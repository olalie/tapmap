"""Dash application entry point for TapMap.

This module wires together the main application layers:

- model: runtime state and data collection (snapshot, GeoIP reload, caches)
- geodb: GeoIP database installation, updates, validation, and status
- state: pure decision logic (no Dash code)
- ui: rendering helpers (map, modal, status text)

app.py contains Dash callback wiring and controller code only.
Deterministic state transitions live in the state package.

Dash callbacks return multiple values because each Output property
requires one return value. For example, modal_controller returns:

    modal_state
    modal_overlay className
    modal_body children
    modal_body className
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import platform
import sys
import threading
import webbrowser
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Final, Literal, TypedDict

import psutil
from dash import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from tapmap import __version__
from tapmap.geodb import GeoDbService
from tapmap.geodb.service import GeoDbResponse
from tapmap.insights_persistence import (
    build_daily_report as persist_build_daily_report,
)
from tapmap.insights_persistence import (
    load_insights,
    save_insights,
)
from tapmap.model.appinfo import AppInfo
from tapmap.model.geoinfo import GeoInfo
from tapmap.model.model import Model
from tapmap.model.netinfo import NetInfo
from tapmap.model.public_ip import iter_public_ip_candidates
from tapmap.settings_persistence import Settings, load_settings, save_settings
from tapmap.state.insights import process_insights
from tapmap.state.insights_log import write_insights_log
from tapmap.state.keyboard import build_key_action
from tapmap.state.menu import compute_menu_open_state
from tapmap.state.modal import decide_modal_route
from tapmap.state.open_ports_prefs import set_show_system_pref
from tapmap.state.poll import (
    ACTION_CLEAR_CACHE,
    ACTION_NORMAL_POLL,
    ACTION_REBUILD_VIEW,
    ACTION_ZOOM_CONNECTIONS,
    decide_poll_action,
)
from tapmap.state.status_cache import StatusCache
from tapmap.state.status_line import render_status_text
from tapmap.ui.cache_view import CacheViewBuilder
from tapmap.ui.daily_activity_report_view import render_daily_activity_report
from tapmap.ui.insights_log_view import render_insights_log
from tapmap.ui.insights_view import render_insights_panel
from tapmap.ui.layout_view import render_layout
from tapmap.ui.map_view import MapUI
from tapmap.ui.modal_view import ModalTextBuilder

from .app_dirs import open_folder, reveal_in_file_manager
from .config import COORD_PRECISION, MY_LOCATION, POLL_INTERVAL_MS, ZOOM_NEAR_KM
from .logging_config import configure_logging
from .runtime import AppMeta, RuntimeContext, build_runtime

LonLat = tuple[float, float]

APP_META: Final[AppMeta] = AppMeta(
    name="TapMap",
    version=__version__,
    author="Ola Lie",
)

class GeoDbEvent(TypedDict):
    """GeoDB action and response payload for UI rendering."""

    action: Literal[
        "install_maxmind",
        "install_dbip",
        "update",
        "recheck",
    ]
    response: GeoDbResponse
    
    
class TapMap:
    """Coordinate Dash callbacks, model polling, and UI state."""

    SCR_GEODB_MANAGEMENT = "menu_geodb_management"

    MENU_SCREENS: ClassVar[frozenset[str]] = frozenset(
        {
            "menu_unmapped",
            "menu_lan_local",
            "menu_open_ports",
            SCR_GEODB_MANAGEMENT,
            "menu_help",
            "menu_about",
            "menu_daily_report",
            "menu_insights_log",
            "menu_exit",
        }
    )
    MENU_COMMANDS: ClassVar[frozenset[str]] = frozenset(
        {"menu_clear_cache", "menu_export_cache"}
    )

    DASH_DEBUG = False
    MIN_FLASH_S = 3.0

    def __init__(self, runtime_ctx: RuntimeContext) -> None:
        self.runtime = runtime_ctx
        self.logger = logging.getLogger(__name__)
        self._lock_path = self.runtime.app_data_dir / "tapmap.lock"
        self._acquire_lock()

        self.app = Dash(
            __name__,
            title=self.runtime.meta.name,
            update_title=None,
            suppress_callback_exceptions=True,
        )

        self.ui = MapUI(zoom_near_km=ZOOM_NEAR_KM)
        self.view_builder = CacheViewBuilder(
            coord_precision=COORD_PRECISION,
            is_docker=self.runtime.is_docker,
            cache_retention_min=self.runtime.cache_retention_min,
        )
        self._ui_cache: dict[str, Any] = {}
        self._status_cache = StatusCache()

        self.modal_text = ModalTextBuilder(
            self.runtime.meta.name,
            self.runtime.meta.version,
            self.runtime.meta.author,
        )
        self.geodb = GeoDbService(self.runtime)

        self.model = Model(
            netinfo=NetInfo(),
            geoinfo=GeoInfo(data_dir=self.runtime.geo_data_dir),
            appinfo=AppInfo(security_extensions_dir=self.runtime.security_extensions_dir),
        )

        self._public_ip_cached: str | None = None
        self._auto_geo_cached: dict[str, Any] = {}

        self.my_location = self._resolve_my_location()

        self.graph_config = {
            "displaylogo": False,
            "scrollZoom": False,
            "modeBarButtonsToRemove": [
                "toImage",
                "select2d",
                "lasso2d",
                "hoverClosestGeo",
                "toggleHover",
            ],
        }

        self.insights: dict[str, Any] = {
            "countries": {},
            "providers": {},
            "ports": {},


            "applications": {},
        }

        self.insights_path = self.runtime.app_data_dir / "insights.json"
        self._load_insights()
        self._last_insights_save = 0.0

        self.settings_path = self.runtime.app_data_dir / "settings.json"
        self.settings: Settings = load_settings(self.settings_path)

        start_fig = self.ui.create_figure(([], self.my_location))
        self.app.layout = self._build_layout(start_fig)
        self._register_callbacks()
        self._poll_count = 0
        self._modal_count = 0
        self._geodb_controller_count = 0

    @staticmethod
    def _menu_panel_class(is_open: bool) -> str:
        return "mx-panel is-open" if is_open else "mx-panel"

    @staticmethod
    def _menu_overlay_class(is_open: bool) -> str:
        return "mx-overlay is-open" if is_open else "mx-overlay"

    @staticmethod
    def _modal_overlay_class(is_open: bool) -> str:
        return "modal-overlay is-open" if is_open else "modal-overlay"

    def _build_layout(self, start_fig: Any) -> html.Div:
        geo_status = self.geodb.local_status()
        geo_ready = geo_status["provider"] != "none"
        initial_modal_state: dict[str, Any] | None = None
        if not geo_ready:
            initial_modal_state = {
                "screen": self.SCR_GEODB_MANAGEMENT,
                "t": datetime.now().isoformat(),
                "payload": {"startup_required": True},
            }

        initial_modal_open = bool(initial_modal_state)

        initial_body_children: list[Any] = []
        initial_body_class = "modal-body"
        if initial_modal_state is not None:
            geo_path = str(self.runtime.geo_data_dir)
            initial_body_children = self._as_children(
                self.modal_text.geodb_management(
                    status=geo_status,
                    geo_data_dir=geo_path,
                    is_docker=self.runtime.is_docker,
                )
            )
            initial_body_class = self._class_for_modal_screen(self.SCR_GEODB_MANAGEMENT)

        return render_layout(
            app_name=self.runtime.meta.name,
            start_fig=start_fig,
            graph_config=self.graph_config,
            poll_interval_ms=POLL_INTERVAL_MS,
            status_cache_store=StatusCache().to_store(),
            initial_modal_state=initial_modal_state,
            initial_modal_open=initial_modal_open,
            initial_body_children=initial_body_children,
            initial_body_class=initial_body_class,
            menu_overlay_class=self._menu_overlay_class(False),
            menu_panel_class=self._menu_panel_class(False),
            modal_overlay_class=self._modal_overlay_class(initial_modal_open),
            initial_insights_on=self.settings.insights_panel,
            initial_technical_details_on=self.settings.technical_details,
        )

    @staticmethod
    def _ensure_dict(value: object) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _ensure_list(value: object) -> list[Any]:
        return value if isinstance(value, list) else []

    @staticmethod
    def _to_int(value: object, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _flash(message: str, seconds: float) -> dict[str, Any]:
        return {"message": message, "until": (datetime.now().timestamp() + float(seconds))}

    def _myloc_label(self) -> str:
        if self.runtime.location_override is not None:
            return "ENV"
        if isinstance(MY_LOCATION, tuple):
            return "FIXED"
        if MY_LOCATION == "none":
            return "OFF"
        if MY_LOCATION == "auto":
            return "AUTO" if self.my_location else "AUTO (NO GEO)"
        return "OFF"

    def _resolve_my_location(self) -> list[LonLat]:
        if self.runtime.location_override is not None:
            return [self.runtime.location_override]

        if isinstance(MY_LOCATION, tuple):
            return [MY_LOCATION]

        if MY_LOCATION == "none":
            return []

        if MY_LOCATION == "auto":
            if not getattr(self.model.geoinfo, "city_enabled", False):
                self._public_ip_cached = None
                self._auto_geo_cached = {}
                return []

            for ip in iter_public_ip_candidates(timeout_s=2.0):
                geo = self.model.geoinfo.lookup(ip)
                geo_dict = geo if isinstance(geo, dict) else {}
                lat = geo_dict.get("lat")
                lon = geo_dict.get("lon")

                if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                    self._public_ip_cached = ip
                    self._auto_geo_cached = dict(geo_dict)
                    return [(float(lon), float(lat))]

            self._public_ip_cached = None
            self._auto_geo_cached = {}
            return []

        return []

    def _build_runtime_info(self) -> dict[str, Any]:
        geo_status = self.geodb.local_status()
        return {
            "version": self.runtime.meta.version,
            "poll_interval_ms": POLL_INTERVAL_MS,
            "coord_precision": COORD_PRECISION,
            "zoom_near_km": ZOOM_NEAR_KM,
            "geoinfo_enabled": bool(getattr(self.model.geoinfo, "city_enabled", False)),
            "geo_data_dir": str(self.runtime.geo_data_dir),
            "app_data_dir": str(self.runtime.app_data_dir),
            "run_dir": str(self.runtime.run_dir),
            "is_frozen": bool(self.runtime.is_frozen),
            "myloc_mode": self._myloc_label(),
            "my_location": (
                self.runtime.location_override
                if self.runtime.location_override is not None
                else MY_LOCATION
            ),
            "public_ip_cached": self._public_ip_cached,
            "auto_geo_cached": self._auto_geo_cached,
            "os": f"{platform.system()} {platform.release()}",
            "python": sys.version.split()[0],
            "net_backend": self.runtime.net_backend,
            "net_backend_version": self.runtime.net_backend_version,
            "server_host": self.runtime.server_host,
            "server_port": self.runtime.server_port,
            "launch_browser": self.runtime.launch_browser,
            "cache_retention_min": self.runtime.cache_retention_min,
            "is_docker": self.runtime.is_docker,
            "geo_provider": geo_status["provider"],
            "geo_database_date": geo_status["local_display_date"]
        }

    def _reload_geodb_runtime(self) -> bool:
        """Reload GeoDB readers and refresh runtime state."""
        geo_status = self.geodb.recheck()
        ok = self.model.geoinfo.reload()
        geo_ready = (
            geo_status["provider"] != "none"
            and self.model.geoinfo.enabled
        )

        if not ok or not geo_ready:
            return False

        self.my_location = self._resolve_my_location()
        return True

    def _reload_after_geodb_operation(
        self,
        response: GeoDbResponse,
    ) -> GeoDbResponse:
        """Reload runtime readers after successful GeoDB operations."""
        # New MMDB files are not used until runtime readers are reloaded.
        if (
            response.get("error") is None
            and not self._reload_geodb_runtime()
        ):
            response["error"] = "reload_failed"
            response["message"] = (
                f'{response.get("message", "")} '
                "Runtime reload failed."
            ).strip()

        return response
    
    def _handle_geo_install_dbip(self) -> GeoDbResponse:
        return self._reload_after_geodb_operation(
            self.geodb.install("dbip")
        )

    def _resolve_maxmind_install_credentials(
        self,
        account_id: Any,
        license_key: Any,
    ) -> tuple[str, str]:
        """Resolve MaxMind credentials using UI values first, then stored values."""
        ui_account_id = account_id.strip() if isinstance(account_id, str) else ""
        ui_license_key = license_key.strip() if isinstance(license_key, str) else ""

        stored_account_id, stored_license_key = self.geodb.maxmind.stored_credentials()
        resolved_account_id = ui_account_id or (stored_account_id or "")
        resolved_license_key = ui_license_key or (stored_license_key or "")
        return resolved_account_id, resolved_license_key

    def _handle_geo_install_maxmind(
        self,
        account_id: Any,
        license_key: Any,
    ) -> GeoDbResponse:
        account_id_text, license_key_text = self._resolve_maxmind_install_credentials(
            account_id,
            license_key,
        )

        try:
            self.geodb.maxmind.validate_credentials(
                account_id_text,
                license_key_text,
            )

        except ValueError as exc:
            status = self.geodb.local_status()
            status["message"] = str(exc)
            status["error"] = "credentials_invalid"
            return status

        try:
            self.geodb.maxmind.register_credentials(
                account_id_text,
                license_key_text,
            )

        except Exception:
            self.logger.exception("Unable to store MaxMind credentials")
            status = self.geodb.local_status()
            status["message"] = "Unable to store MaxMind credentials"
            status["error"] = "credential_store_failed"
            return status

        return self._reload_after_geodb_operation(
            self.geodb.install("maxmind")
        )
    
    def _handle_geo_update(self) -> GeoDbResponse:
        return self._reload_after_geodb_operation(
            self.geodb.update()
        )
    
    def _handle_geo_recheck(self) -> GeoDbResponse:
        return self._reload_after_geodb_operation(
            self.geodb.recheck()
        )
   
    def _handle_clear_cache(
        self, status_cache: StatusCache, technical_details_enabled: bool
    ) -> tuple[Any, Any, Any, Any, Any]:
        """Reset the runtime cache without observing the monitored system."""
        status_cache.clear()
        empty_cache: dict[str, Any] = {}
        view = self.view_builder.build_view_from_cache(empty_cache, technical_details_enabled)
        flash = self._flash("Clearing cache...", self.MIN_FLASH_S)
        return no_update, empty_cache, status_cache.to_store(), view, flash

    def _handle_normal_poll(
        self,
        tick_n: int,
        status_cache: StatusCache,
        ui_cache: dict[str, Any],
        technical_details_enabled: bool,
    ) -> tuple[Any, Any, Any, Any, Any]:
        snap = self.model.snapshot()
        if not isinstance(snap, dict):
            view = self.view_builder.build_view_from_cache(ui_cache, technical_details_enabled)
            flash = self._flash("Model snapshot is invalid. See terminal.", self.MIN_FLASH_S)
            return {"error": True}, ui_cache, status_cache.to_store(), view, flash

        snap["runtime_info"] = self._build_runtime_info()

        if snap.get("error"):
            view = self.view_builder.build_view_from_cache(ui_cache, technical_details_enabled)
            return snap, ui_cache, status_cache.to_store(), view, no_update

        candidates_any = snap.get("map_candidates")
        candidates = candidates_any if isinstance(candidates_any, list) else []
        updated_cache = self.view_builder.merge_map_candidates(ui_cache, candidates)

        items_any = snap.get("cache_items")
        items = items_any if isinstance(items_any, list) else []
        status_cache.update(items)
        view = self.view_builder.build_view_from_cache(updated_cache, technical_details_enabled)
        self._maybe_save_insights()

        return snap, updated_cache, status_cache.to_store(), view, no_update

    def _open_browser(self, url: str, delay_s: float = 0.8) -> None:
        try:
            delay = float(delay_s)
        except (TypeError, ValueError):
            delay = 0.8

        def _worker() -> None:
            try:
                webbrowser.open(url, new=2)
            except Exception:
                return

        timer = threading.Timer(delay, _worker)
        timer.daemon = True
        timer.start()

    @staticmethod
    def _as_children(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    def _class_for_modal_screen(self, screen: str | None) -> str:
        if screen in {
            "menu_unmapped",
            "menu_lan_local",
            "menu_open_ports",
            self.SCR_GEODB_MANAGEMENT,
            "menu_help",
            "menu_about",
        }:
            return "modal-body mx-sticky-title"
        return "modal-body"

    @staticmethod
    def _toggle_on(value: Any) -> bool:
        return isinstance(value, list) and "on" in value

    @staticmethod
    def _startup_geodb_modal_should_close(
        modal_state: dict[str, Any] | None,
        snapshot: Any,
    ) -> bool:
        """Return True when the startup GeoDB modal should close after a successful install."""
        if not isinstance(modal_state, dict):
            return False

        payload = modal_state.get("payload")
        payload_data = payload if isinstance(payload, dict) else {}
        if not bool(payload_data.get("startup_required", False)):
            return False

        snapshot_data = snapshot if isinstance(snapshot, dict) else {}
        snapshot_runtime_info = snapshot_data.get("runtime_info")
        runtime_info = snapshot_runtime_info if isinstance(snapshot_runtime_info, dict) else {}
        return bool(runtime_info.get("geoinfo_enabled", False))

    def _render_modal(
        self,
        modal_state: dict[str, Any] | None,
        snapshot: Any,
        ui_view: Any,
        geo_path: str,
        geodb_event: dict[str, Any] | None,
    ) -> tuple[list[Any], str]:
        
        if not isinstance(modal_state, dict):
            return [], "modal-body"

        screen = modal_state.get("screen")
        payload = self._ensure_dict(modal_state.get("payload"))
        modal_opened_at = modal_state.get("t")

        if not isinstance(screen, str) or not screen:
            return [], "modal-body"

        if screen == self.SCR_GEODB_MANAGEMENT:
            children = self._as_children(
                self.modal_text.geodb_management(
                    status=self.geodb.local_status(),
                    geo_data_dir=geo_path,
                    is_docker=self.runtime.is_docker,
                    geodb_event=geodb_event,
                    modal_opened_at=modal_opened_at,
                )
            )
            return children, self._class_for_modal_screen(screen)

        if screen == "map_click":
            click_data = payload.get("click_data")
            body = self.modal_text.for_click(click_data, ui_view)
            if body is None:
                return [], "modal-body"
            return self._as_children(body), "modal-body"

        if screen == "menu_daily_report":
            report = persist_build_daily_report(self.insights)
            return (
                render_daily_activity_report(report),
                self._class_for_modal_screen(screen),
            )

        if screen == "menu_insights_log":
            log_path = self.insights_path.with_suffix(".log")
            text = ""
            with contextlib.suppress(Exception):
                write_insights_log(self.insights, log_path)
                text = log_path.read_text(encoding="utf-8")
            return (
                render_insights_log(text),
                self._class_for_modal_screen(screen),
            )

        if screen == "menu_exit":
            return (
                [
                    html.H1("TapMap has stopped"),
                    html.Div(
                        id="shutdown_screen",
                        children=[
                            html.P("Network monitoring has ended."),
                            html.P("You may now close this browser tab."),
                            html.P("Start TapMap to begin monitoring again."),
                        ],
                    ),
                ],
                "modal-body no-close",
            )

        if screen in self.MENU_SCREENS:
            show_system = bool(payload.get("show_system", False))
            body = self.modal_text.for_action(
                screen,
                snapshot=snapshot,
                show_system=show_system,
                is_docker=self.runtime.is_docker,
            )
            return self._as_children(body), self._class_for_modal_screen(screen)

        return [], "modal-body"

    def _register_callbacks(self) -> None:
        self._register_keyboard_callbacks()
        self._register_poll_callbacks()
        self._register_menu_callbacks()
        self._register_modal_callbacks()
        self._register_geodb_callbacks()
        self._register_modal_render_callbacks()
        self._register_map_callbacks()
        self._register_status_callbacks()
        self._register_insights_callbacks()
        self._register_os_callbacks()

    def _register_keyboard_callbacks(self) -> None:
        @self.app.callback(
            Output("key_action", "data"),
            Output("key_capture", "value"),
            Input("key_capture", "value"),
            prevent_initial_call=True,
        )
        def on_key(value: str) -> tuple[Any, str]:
            action = build_key_action(value)
            if action is None:
                return no_update, ""
            return action, ""

    def _register_poll_callbacks(self) -> None:
        @self.app.callback(
            Output("model_snapshot", "data"),
            Output("status_cache", "data"),
            Output("ui_view", "data"),
            Output("status_flash", "data"),
            Input("tick_model", "n_intervals"),
            Input("key_action", "data"),
            Input("menu_clear_cache", "n_clicks"),
            State("status_flash", "data"),
            State("technical_details_on", "data"),
            prevent_initial_call=True,
        )
        def poll_model(
            tick_n: int,
            key_action: Any,
            _clear_clicks: int,
            status_flash_data: Any,
            technical_details_data: Any,
        ):
            status_cache = self._status_cache
            ui_cache = self._ui_cache
            technical_details_enabled = bool(technical_details_data)
            trigger = ctx.triggered_id
            decision = decide_poll_action(
                trigger=trigger,
                key_action=key_action,
            )

            if decision.action == ACTION_CLEAR_CACHE:
                snap, cache, sc_store, view, flash = self._handle_clear_cache(
                    status_cache, technical_details_enabled
                )
                self._ui_cache = cache
                return snap, sc_store, view, flash

            if decision.action == ACTION_NORMAL_POLL:
                snap, cache, sc_store, view, _flash = self._handle_normal_poll(
                    tick_n, status_cache, ui_cache, technical_details_enabled
                )
                self._ui_cache = cache

                now = datetime.now().timestamp()
                if isinstance(status_flash_data, dict):
                    until = status_flash_data.get("until")
                    if isinstance(until, (int, float)) and now < until:
                        return snap, sc_store, view, no_update

                return snap, sc_store, view, None

            if decision.action == ACTION_REBUILD_VIEW:
                view = self.view_builder.build_view_from_cache(
                    self._ui_cache, technical_details_enabled
                )
                return no_update, no_update, view, no_update

            return no_update, no_update, no_update, no_update

    def _register_menu_callbacks(self) -> None:
        @self.app.callback(
            Output("menu_open", "data"),
            Output("insights_on", "data"),
            Output("technical_details_on", "data"),
            Input("btn_menu", "n_clicks"),
            Input("menu_overlay", "n_clicks"),
            Input("key_action", "data"),
            Input("menu_insights", "n_clicks"),
            Input("menu_technical_details", "n_clicks"),
            Input("menu_daily_report", "n_clicks"),
            Input("menu_open_ports", "n_clicks"),
            Input("menu_unmapped", "n_clicks"),
            Input("menu_lan_local", "n_clicks"),
            Input("menu_export_cache", "n_clicks"),
            Input("menu_geodb_management", "n_clicks"),
            Input("menu_about", "n_clicks"),
            Input("menu_help", "n_clicks"),
            Input("menu_clear_cache", "n_clicks"),
            Input("menu_exit", "n_clicks"),
            State("menu_open", "data"),
            State("insights_on", "data"),
            State("technical_details_on", "data"),
            prevent_initial_call=True,
        )
        def menu_controller(
            _btn: int,
            _overlay: int,
            key_action: Any,
            _insights: int,
            _technical_details: int,
            _daily_report: int,
            _open_ports: int,
            _unmapped: int,
            _lan_local: int,
            _export_cache: int,
            _geodb_management: int,
            _info: int,
            _help: int,
            _clear: int,
            _exit: int,
            menu_open: Any,
            insights_on: Any,
            technical_details_on: Any,
        ) -> Any:
            trigger = ctx.triggered_id

            if trigger == "menu_insights" or (
                trigger == "key_action"
                and isinstance(key_action, dict)
                and key_action.get("action") == "menu_insights"
            ):
                new_value = not bool(insights_on)
                self.settings = replace(self.settings, insights_panel=new_value)
                self._save_settings()
                return False, new_value, no_update

            if trigger == "menu_technical_details" or (
                trigger == "key_action"
                and isinstance(key_action, dict)
                and key_action.get("action") == "menu_technical_details"
            ):
                new_value = not bool(technical_details_on)
                self.settings = replace(self.settings, technical_details=new_value)
                self._save_settings()
                return False, no_update, new_value

            next_state = compute_menu_open_state(
                trigger=trigger,
                menu_open=menu_open,
                key_action=key_action,
                menu_screens=self.MENU_SCREENS,
                menu_commands=self.MENU_COMMANDS,
            )

            if next_state is None:
                return no_update, no_update, no_update
            return next_state, no_update, no_update

        @self.app.callback(
            Output("menu_panel", "className"),
            Output("menu_overlay", "className"),
            Input("menu_open", "data"),
        )
        def show_hide_menu(is_open: Any) -> tuple[str, str]:
            open_flag = bool(is_open)
            return self._menu_panel_class(open_flag), self._menu_overlay_class(open_flag)

        @self.app.callback(
            Output("insights_panel", "className"),
            Input("insights_on", "data"),
        )
        def toggle_insights_panel(is_on: Any) -> str:
            if bool(is_on):
                return "insights-panel is-open"
            return "insights-panel"

        @self.app.callback(
            Output("menu_insights", "className"),
            Input("insights_on", "data"),
        )
        def toggle_insights_check(is_on: Any) -> str:
            if bool(is_on):
                return "mx-btn mx-btn--menu mx-btn--toggle is-checked"
            return "mx-btn mx-btn--menu mx-btn--toggle"

        @self.app.callback(
            Output("menu_technical_details", "className"),
            Input("technical_details_on", "data"),
        )
        def toggle_technical_details_check(is_on: Any) -> str:
            if bool(is_on):
                return "mx-btn mx-btn--menu mx-btn--toggle is-checked"
            return "mx-btn mx-btn--menu mx-btn--toggle"

        @self.app.callback(
            Output("map", "style"),
            Input("insights_on", "data"),
        )
        def resize_map(is_on: Any) -> dict[str, str]:
            if bool(is_on):
                return {"width": "calc(100% - 270px)"}
            return {"width": "100%"}

    def _register_geodb_callbacks(self) -> None:
        @self.app.callback(
            Output("geodb_event", "data"),
            Input("btn_install_dbip", "n_clicks", allow_optional=True),
            Input("btn_install_maxmind", "n_clicks", allow_optional=True),
            Input("btn_update_databases", "n_clicks", allow_optional=True),
            Input("btn_check_databases", "n_clicks", allow_optional=True),
            State("input_maxmind_account_id", "value", allow_optional=True),
            State("input_maxmind_license_key", "value", allow_optional=True),
            running=[
                (Output("btn_install_dbip", "disabled"), True, False),
                (Output("btn_install_maxmind", "disabled"), True, False),
                (Output("btn_update_databases", "disabled"), True, False),
                (Output("btn_check_databases", "disabled"), True, False),
],
            prevent_initial_call=True,
        )
        def geodb_controller(
            install_dbip_clicks: int | None,
            install_maxmind_clicks: int | None,
            update_clicks: int | None,
            check_clicks: int | None,
            account_id: str | None,
            license_key: str | None,
        ) -> GeoDbEvent:
            trigger = ctx.triggered_id

            if trigger == "btn_install_dbip":
                if not install_dbip_clicks:
                    raise PreventUpdate

                response = self._handle_geo_install_dbip()
                return {"action": "install_dbip", "response": response}

            if trigger == "btn_install_maxmind":
                if not install_maxmind_clicks:
                    raise PreventUpdate

                response = self._handle_geo_install_maxmind(account_id, license_key)
                return {"action": "install_maxmind", "response": response}

            if trigger == "btn_update_databases":
                if not update_clicks:
                    raise PreventUpdate

                response = self._handle_geo_update()
                return {"action": "update", "response": response}

            if trigger == "btn_check_databases":
                if not check_clicks:
                    raise PreventUpdate

                response = self._handle_geo_recheck()
                return {"action": "recheck", "response": response}
    
            raise PreventUpdate
        
    def _register_os_callbacks(self) -> None:
        @self.app.callback(
            Input("btn_open_data", "n_clicks", allow_optional=True),
            prevent_initial_call=True,
        )
        def open_data_folder(n_clicks: int | None) -> None:
            if not n_clicks:
                raise PreventUpdate

            if self.runtime.is_docker:
                return

            ok, message = open_folder(self.runtime.geo_data_dir)

            if not ok:
                self.logger.warning(message)

        @self.app.callback(
            Input({"type": "reveal-exe", "path": ALL, "idx": ALL}, "n_clicks"),
            prevent_initial_call=True,
        )
        def reveal_executable(_clicks: list[int | None]) -> None:
            trigger_id = ctx.triggered_id
            if not isinstance(trigger_id, dict):
                raise PreventUpdate

            path = trigger_id.get("path")
            if not isinstance(path, str) or not path:
                raise PreventUpdate

            if self.runtime.is_docker:
                return

            ok, message = reveal_in_file_manager(Path(path))

            if not ok:
                self.logger.warning(message)

        @self.app.callback(
            Output("cache_download", "data"),
            Input("menu_export_cache", "n_clicks"),
            Input("key_action", "data"),
            prevent_initial_call=True,
        )
        def export_cache(
            n_clicks: int | None,
            key_action: Any,
        ) -> Any:
            trigger = ctx.triggered_id
            if trigger == "key_action":
                if not (
                    isinstance(key_action, dict) and key_action.get("action") == "menu_export_cache"
                ):
                    raise PreventUpdate
            elif not n_clicks:
                raise PreventUpdate
            now = datetime.now()
            filename = f"tapmap-cache-{now.strftime('%Y-%m-%d_%H-%M-%S')}.txt"
            header = f"TapMap Cache Export\nGenerated: {now.strftime('%Y-%m-%d %H:%M:%S')}"
            return dcc.send_string(
                self._status_cache.format_ui_cache_text(self._ui_cache, header=header), filename
            )

        @self.app.callback(
            Input("key_action", "data"),
            prevent_initial_call=True,
        )
        def exit_app(key_action: Any) -> None:
            if not (isinstance(key_action, dict) and key_action.get("action") == "exit_confirmed"):
                raise PreventUpdate
            self.close()
            logging.shutdown()
            os._exit(0)

    def _register_modal_render_callbacks(self) -> None:
        @self.app.callback(
            Output("modal_overlay", "className"),
            Output("modal_body", "children"),
            Output("modal_body", "className"),
            Input("modal_state", "data"),
            Input("geodb_event", "data"),
            State("ui_view", "data"),
            State("model_snapshot", "data"),
            prevent_initial_call=False,
        )
        def modal_renderer(
            modal_state_data: Any,
            geodb_event_data: Any,
            ui_view: Any,
            snapshot: Any,
        ):
            geo_path = str(self.runtime.geo_data_dir)

            children, body_class = self._render_modal(
                modal_state_data,
                snapshot,
                ui_view,
                geo_path,
                geodb_event_data,
            )

            overlay_class = self._modal_overlay_class(
                isinstance(modal_state_data, dict)
            )

            return overlay_class, children, body_class
        
    def _register_modal_callbacks(self) -> None:
        @self.app.callback(
            Output("modal_state", "data"),
            Input("menu_open_ports", "n_clicks"),
            Input("menu_unmapped", "n_clicks"),
            Input("menu_lan_local", "n_clicks"),
            Input("menu_geodb_management", "n_clicks"),
            Input("menu_about", "n_clicks"),
            Input("menu_help", "n_clicks"),
            Input("menu_daily_report", "n_clicks"),
            Input("menu_exit", "n_clicks"),
            Input("btn_close", "n_clicks"),
            Input("toggle_open_ports_system", "value", allow_optional=True),
            Input("map", "clickData"),
            Input("btn_view_log", "n_clicks", allow_optional=True),
            Input("btn_log_back", "n_clicks", allow_optional=True),
            Input("key_action", "data"),
            State("modal_state", "data"),
            State("open_ports_prefs", "data"),
            prevent_initial_call=True,
        )
        def modal_controller(
            _open_ports_clicks: int,
            _unmapped_clicks: int,
            _lan_local_clicks: int,
            _geodb_management_clicks: int,
            _about_clicks: int,
            _help_clicks: int,
            _daily_report_clicks: int,
            _exit_clicks: int,
            _close_clicks: int,
            toggle_system_value: Any,
            click_data: Any,
            _view_log_clicks: int | None,
            _log_back_clicks: int | None,
            key_action: Any,
            modal_state_data: Any,
            open_ports_prefs_data: Any,
        ):
            current_state = modal_state_data if isinstance(modal_state_data, dict) else None
            current_screen = (
                current_state.get("screen") if isinstance(current_state, dict) else None
            )
            trigger = ctx.triggered_id
       
            if trigger == "btn_close":
                return None

            is_open = current_state is not None
            action = None

            if trigger == "key_action" and isinstance(key_action, dict):
                action = key_action.get("action")

            now_iso = datetime.now().isoformat()
            open_ports_prefs = (
                open_ports_prefs_data if isinstance(open_ports_prefs_data, dict) else None
            )
            route = decide_modal_route(
                trigger=trigger,
                is_open=is_open,
                current_screen=current_screen if isinstance(current_screen, str) else None,
                action=action,
                show_system=self._toggle_on(toggle_system_value),
                menu_screens=self.MENU_SCREENS,
                open_ports_prefs=open_ports_prefs,
                click_data=click_data,
                now_iso=now_iso,
            )

            if route.action == "apply":
                return route.modal_state
              
            return no_update

        @self.app.callback(
            Output("open_ports_prefs", "data"),
            Input("toggle_open_ports_system", "value", allow_optional=True),
            State("open_ports_prefs", "data"),
            prevent_initial_call=True,
        )
        def open_ports_toggle(toggle_value: Any, prefs_data: Any) -> dict[str, Any]:
            return set_show_system_pref(toggle_value=toggle_value, prefs_data=prefs_data)

    def _register_map_callbacks(self) -> None:
        @self.app.callback(
            Output("map", "figure"),
            Input("ui_view", "data"),
            Input("selected_country", "data"),
            Input("camera_mode", "data"),
        )
        def render_map(ui_view: Any, selected_country: Any, camera_mode: Any) -> Any:
            view = self._ensure_dict(ui_view)
            fit_connections = (camera_mode == "connections")

            if "points" not in view:
                return no_update

            points = self._ensure_list(view.get("points"))
            summaries = self._ensure_dict(view.get("summaries"))

            if not points:
                return self.ui.create_figure(
                    ([], self.my_location),
                    summaries=summaries,
                    selected_country=selected_country,
                    fit_connections=fit_connections,
                )

            return self.ui.create_figure(
                (points, self.my_location),
                summaries=summaries,
                selected_country=selected_country,
                fit_connections=fit_connections,
            )

        @self.app.callback(
            Output("selected_country", "data"),
            Output("camera_mode", "data"),
            Input("key_action", "data"),
            Input(
                {
                    "type": "insights-country",
                    "country_code": ALL,
                    "section": ALL,
                },
                "n_clicks",
            ),
            State("selected_country", "data"),
            State("camera_mode", "data"),
            prevent_initial_call=True,
        )
        def update_map_state(
            key_action: Any,
            _clicks_country: list[int],
            current_country: Any,
            current_camera_mode: Any,
        ) -> tuple[Any, Any]:

            trigger_id = ctx.triggered_id

            # Keyboard
            if trigger_id == "key_action":
                if (
                    isinstance(key_action, dict)
                    and key_action.get("action") == ACTION_ZOOM_CONNECTIONS
                ):
                    if current_camera_mode == "connections":
                        return None, None

                    return None, "connections"

                return no_update, no_update

            # Country selection
            current = current_country if isinstance(current_country, str) else None

            if not ctx.triggered:
                return no_update, no_update

            trigger = ctx.triggered[0]
            if not trigger["value"]:
                return no_update, no_update

            if not isinstance(trigger_id, dict):
                return no_update, no_update

            country_code = trigger_id.get("country_code")
            if not isinstance(country_code, str):
                return no_update, no_update

            if current == country_code:
                return None, None

            return country_code, None
        
    def _register_status_callbacks(self) -> None:
        @self.app.callback(
            Output("status_bar", "children"),
            Input("model_snapshot", "data"),
            Input("status_cache", "data"),
            Input("status_flash", "data"),
        )
        def render_status(
            snapshot: Any,
            status_cache_data: Any,
            status_flash: Any,
        ) -> str:
            return render_status_text(
                snapshot=snapshot,
                status_cache_data=status_cache_data,
                status_flash=status_flash,
                myloc_label=self._myloc_label(),
                to_int=self._to_int,
            )

    def _register_insights_callbacks(self) -> None:
        @self.app.callback(
            Output("insights_panel", "children"),
            Input("insights_cache", "data"),
            Input("selected_country", "data"),
        )
        def update_insights(
            data: dict[str, Any] | None,
            selected_country: Any,
        ) -> list[Any]:

            if not isinstance(data, dict):
                return []

            return render_insights_panel(data, selected_country=selected_country)

        @self.app.callback(
            Output("insights_cache", "data"),
            Input("model_snapshot", "data"),
        )
        def update_insights_data(snapshot: Any) -> Any:

            if not isinstance(snapshot, dict):
                return {"new": {}, "top": {}}

            now = datetime.now()

            return process_insights(
                snapshot.get("cache_items", []),
                self.insights,
                now,
            )

    def run(self) -> None:
        """Start the Dash server and launch the local UI."""
        host = self.runtime.server_host
        port = self.runtime.server_port
        url = f"http://{host}:{port}/"
        if self.runtime.launch_browser and not self.runtime.is_docker:
            self._open_browser(url)

        self.logger.info(
            "Starting %s %s on %s",
            self.runtime.meta.name,
            self.runtime.meta.version,
            url,
            extra={"section_break": True},
        )
        self.app.run(
            host=host,
            port=port,
            debug=self.DASH_DEBUG,
            use_reloader=False,
        )

    @staticmethod
    def _empty_insights() -> dict[str, Any]:
        return {"countries": {}, "providers": {}, "ports": {}, "applications": {}}

    def _load_insights(self) -> None:
        """Load insights data from JSON file into memory (delegated)."""
        try:
            self.insights = load_insights(self.insights_path)
        except Exception as exc:
            self.logger.warning(
                "Unable to load insights. Starting with empty history. Reason: %s",
                exc,
            )
            self.insights = self._empty_insights()

    def _maybe_save_insights(self) -> None:
        """Save insights periodically to limit disk writes."""
        now = datetime.now().timestamp()

        if now - self._last_insights_save >= 60:
            self._last_insights_save = now
            self._save_insights()

    def _save_settings(self) -> None:
        """Write settings data to disk atomically."""
        try:
            save_settings(self.settings_path, self.settings)
        except Exception as exc:
            self.logger.warning(
                "Unable to save settings. Changes will not be preserved. Reason: %s",
                exc,
            )

    def _save_insights(self) -> None:
        """Write insights data to disk atomically (delegated)."""
        try:
            save_insights(self.insights_path, self.insights)
        except Exception as exc:
            self.logger.warning(
                "Unable to save insights. Changes will not be preserved. Reason: %s",
                exc,
            )

    def _acquire_lock(self) -> None:
        """Write a lock file, or exit if another instance is already running."""
        # Prevent multiple TapMap instances from accessing the same
        # application data files simultaneously. The lock file stores
        # the creator's PID and process start time. The PID locates the
        # process, while create_time confirms that it is the same process
        # because operating systems may reuse PIDs.
        if self._lock_path.exists():
            try:
                lock = json.loads(self._lock_path.read_text(encoding="utf-8"))

                if (
                    isinstance(lock, dict)
                    and "pid" in lock
                    and "create_time" in lock
                ):
                    running_process = psutil.Process(int(lock["pid"]))

                    if running_process.create_time() == float(lock["create_time"]):
                        self.logger.warning(
                            "Another TapMap instance is already running (PID %d). Exiting.",
                            running_process.pid,
                        )
                        sys.exit(1)

            except (
                OSError,
                json.JSONDecodeError,
                psutil.NoSuchProcess,
            ):
                pass

        current_process = psutil.Process()

        self._lock_path.write_text(
            json.dumps(
                {
                    "pid": current_process.pid,
                    "create_time": current_process.create_time(),
                }
            ),
            encoding="utf-8",
        )

    def _release_lock(self) -> None:
        """Remove the PID lock file."""
        with contextlib.suppress(OSError):
            self._lock_path.unlink(missing_ok=True)

    def close(self) -> None:
        """Close model resources."""
        self.logger.info("Shutting down")
        self._save_insights()
        self._release_lock()
        close_fn = getattr(self.model.geoinfo, "close", None)
        if callable(close_fn):
            close_fn()


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build command-line parser."""
    parser = argparse.ArgumentParser(
        prog="tapmap",
        description="Start TapMap.",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {APP_META.version}",
        help="Show installed version and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run application from the command line."""
    _build_arg_parser().parse_args(argv)
    runtime_ctx = build_runtime(APP_META)
    configure_logging(runtime_ctx)
    app = TapMap(runtime_ctx)
    try:
        app.run()
    finally:
        app.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
