from __future__ import annotations

import logging
import platform
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Final

from dash import Dash, Input, Output, State, ctx, dcc, html, no_update

from app_dirs import open_folder
from config import COORD_PRECISION, MY_LOCATION, POLL_INTERVAL_MS, ZOOM_NEAR_KM
from model.geoinfo import GeoInfo
from model.model import Model
from model.netinfo import NetInfo
from model.public_ip import iter_public_ip_candidates
from runtime import AppMeta, RuntimeContext, build_runtime
from ui.cache_view import CacheViewBuilder
from ui.map_view import MapUI
from ui.modal_view import ModalTextBuilder
from ui.status_cache import StatusCache

LonLat = tuple[float, float]

APP_META: Final[AppMeta] = AppMeta(name="TapMap", version="v1.0", author="Ola Lie")


class TapMap:
    """Coordinate Dash callbacks, model polling, and UI state."""

    MENU_SCREENS: ClassVar[frozenset[str]] = frozenset(
        {"menu_unmapped", "menu_lan_local", "menu_open_ports","menu_help", "menu_about"}
    )
    MENU_COMMANDS: ClassVar[frozenset[str]] = frozenset(
        {"menu_clear", "menu_cache_terminal", "menu_recheck_geo"}
    )

    DASH_DEBUG = False
    DEBUG_COORDS = False
    DEBUG_COORDS_EVERY_N_TICKS = 6

    MODEL_TICK_MS = 5000
    UI_TICK_MS = 500

    FLASH_SHORT_S = 1.5
    FLASH_LONG_S = 3.0

    EVT_GEO_RECHECK = "geo_recheck"
    SCR_MISSING_GEO_DB = "missing_geo_db"

    def __init__(self, runtime_ctx: RuntimeContext) -> None:
        self.ctx = runtime_ctx
        self.logger = logging.getLogger(__name__)

        self.app = Dash(
            __name__,
            title=self.ctx.meta.name,
            update_title=None,
            suppress_callback_exceptions=True,
        )

        self.ui = MapUI(debug=self.DEBUG_COORDS)
        self.view_builder = CacheViewBuilder(
            coord_precision=COORD_PRECISION,
            debug=self.DEBUG_COORDS,
        )

        self.modal_text = ModalTextBuilder(
            self.ctx.meta.name,
            self.ctx.meta.version,
            self.ctx.meta.author,
        )

        self.model = Model(
            netinfo=NetInfo(),
            geoinfo=GeoInfo(data_dir=self.ctx.geo_data_dir),
        )

        self.logger.info(
            "GeoInfo enabled at startup: %s", getattr(self.model.geoinfo, "enabled", False)
        )
        self.logger.info("geo_data_dir: %s", self.ctx.geo_data_dir)

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

        start_fig = self.ui.create_figure(([], self.my_location))
        self.app.layout = self._build_layout(start_fig)
        self._register_callbacks()

    # ----------------------------
    # Layout helpers (CSS classes)
    # ----------------------------

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
        geo_ready = bool(getattr(self.model.geoinfo, "city_enabled", False))

        initial_modal_state: dict[str, Any] | None = None
        if not geo_ready:
            initial_modal_state = {
                "screen": self.SCR_MISSING_GEO_DB,
                "t": datetime.now().isoformat(),
                "payload": {},
            }

        initial_modal_open = bool(initial_modal_state)

        initial_body_children: list[Any] = []
        initial_body_class = "modal-body"
        if initial_modal_state is not None:
            geo_path = str(self.ctx.geo_data_dir)
            initial_body_children = self._as_children(self.modal_text.missing_geo_db(geo_path))
            initial_body_class = self._class_for_modal_screen(self.SCR_MISSING_GEO_DB)

        return html.Div(
            className="app",
            children=[
                dcc.Store(id="menu_open", data=False),
                dcc.Store(id="key_action", data=None),
                dcc.Store(id="status_flash", data=None),
                dcc.Store(id="model_snapshot", data=None),
                dcc.Store(id="ui_cache", data={}),
                dcc.Store(id="status_cache", data=StatusCache().to_store()),
                dcc.Store(id="ui_view", data={"points": [], "summaries": {}, "details": {}}),
                dcc.Store(id="ui_event", data=None),
                dcc.Store(id="ui_event_seen", data=None),
                dcc.Store(id="modal_state", data=initial_modal_state),
                dcc.Store(id="open_ports_prefs", data={"show_system": False}),
                dcc.Input(
                    id="key_capture",
                    type="text",
                    value="",
                    autoFocus=False,
                    style={
                        "position": "fixed",
                        "left": "0",
                        "top": "0",
                        "width": "1px",
                        "height": "1px",
                        "opacity": "0",
                        "zIndex": "1000",
                        "pointerEvents": "none",
                    },
                ),
                dcc.Interval(id="tick_status", interval=self.MODEL_TICK_MS, n_intervals=0),
                dcc.Interval(id="tick_ui", interval=self.UI_TICK_MS, n_intervals=0),
                dcc.Graph(
                    id="map",
                    figure=start_fig,
                    className="map",
                    config=self.graph_config,
                    clear_on_unhover=True,
                ),
                html.Div(self.ctx.meta.name, className="app-title"),
                html.Button(
                    "☰",
                    id="btn_menu",
                    n_clicks=0,
                    className="mx-btn mx-btn--icon",
                    type="button",
                ),
                html.Div(
                    id="menu_overlay",
                    n_clicks=0,
                    className=self._menu_overlay_class(False),
                ),
                html.Nav(
                    id="menu_panel",
                    className=self._menu_panel_class(False),
                    children=[
                        html.Div("Actions", className="mx-panel__title"),
                        html.Div(
                            [
                                self._menu_button(
                                    "Show unmapped public services (U)", "menu_unmapped"
                                ),
                                self._menu_button(
                                    "Show established LAN/LOCAL services (L)", "menu_lan_local"
                                ),
                                self._menu_button(
                                    "Show open ports (O)", "menu_open_ports"
                                ),
                                self._menu_button(
                                    "Show cache in terminal (T)", "menu_cache_terminal"
                                ),
                                self._menu_button("Clear cache (C)", "menu_clear"),
                            ],
                            className="mx-menu-group",
                        ),
                        html.Div(
                            [
                                self._menu_button(
                                    "Recheck GeoIP databases (R)", "menu_recheck_geo"
                                ),
                                self._menu_button("Help (H)", "menu_help"),
                                self._menu_button("About (A)", "menu_about"),
                            ],
                            className="mx-menu-group",
                        ),
                    ],
                ),
                html.Div(
                    id="modal_overlay",
                    className=self._modal_overlay_class(initial_modal_open),
                    children=[
                        html.Div(
                            className="modal-card",
                            children=[
                                html.Div(
                                    id="modal_body",
                                    className=initial_body_class,
                                    children=initial_body_children,
                                ),
                                html.Div(
                                    className="mx-modal-actions",
                                    children=[
                                        html.Button(
                                            "Close",
                                            id="btn_close",
                                            n_clicks=0,
                                            className="mx-btn mx-btn--primary mx-btn--nowrap",
                                            type="button",
                                        ),
                                    ],
                                ),
                            ],
                        )
                    ],
                ),
                html.Div(
                    id="status_bar",
                    className="status-bar",
                    children=(
                        "STATUS: WAIT | "
                        "LIVE: TCP 0 EST 0 LST 0 UDP R 0 B 0 | "
                        "CACHE: SOCK 0 SERV 0 MAP 0 UNM 0 LOC 0 | "
                        "UPDATED: --:--:-- | "
                        "MYLOC: --"
                    ),
                ),
            ],
        )

    def _menu_button(self, label: str, btn_id: str) -> html.Button:
        return html.Button(
            label,
            id=btn_id,
            n_clicks=0,
            className="mx-btn mx-btn--menu",
            type="button",
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

    def _event_signature(self, ev: Any) -> str | None:
        if not isinstance(ev, dict):
            return None
        et = ev.get("type")
        t = ev.get("t")
        if isinstance(et, str) and et:
            return f"{et}|{t}" if isinstance(t, str) else f"{et}|"
        return None

    def _myloc_label(self) -> str:
        if isinstance(MY_LOCATION, tuple):
            return "FIXED"
        if MY_LOCATION == "none":
            return "OFF"
        if MY_LOCATION == "auto":
            return "AUTO" if self.my_location else "AUTO (NO GEO)"
        return "OFF"

    def _resolve_my_location(self) -> list[LonLat]:
        if isinstance(MY_LOCATION, tuple):
            return [MY_LOCATION]

        if MY_LOCATION == "none":
            return []

        if MY_LOCATION == "auto":
            if not getattr(self.model.geoinfo, "city_enabled", False):
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

        return []

    def _build_app_info(self) -> dict[str, Any]:
        return {
            "version": self.ctx.meta.version,
            "poll_interval_ms": POLL_INTERVAL_MS,
            "coord_precision": COORD_PRECISION,
            "zoom_near_km": ZOOM_NEAR_KM,
            "geoinfo_enabled": bool(getattr(self.model.geoinfo, "city_enabled", False)),
            "geo_data_dir": str(self.ctx.geo_data_dir),
            "app_data_dir": str(self.ctx.app_data_dir),
            "run_dir": str(self.ctx.run_dir),
            "is_frozen": bool(self.ctx.is_frozen),
            "myloc_mode": self._myloc_label(),
            "my_location": MY_LOCATION,
            "public_ip_cached": self._public_ip_cached,
            "auto_geo_cached": self._auto_geo_cached,
            "os": f"{platform.system()} {platform.release()}",
            "python": sys.version.split()[0],
            "net_backend": self.ctx.net_backend,
            "net_backend_version": self.ctx.net_backend_version,
        }

    def _handle_geo_recheck(self, status_cache: StatusCache) -> tuple[Any, Any, Any, Any, Any]:
        ok = bool(getattr(self.model.geoinfo, "reload", lambda: False)())
        city_ready = bool(getattr(self.model.geoinfo, "city_enabled", False))

        if not ok or not city_ready:
            snap = self.model.snapshot()
            if isinstance(snap, dict):
                snap["app_info"] = self._build_app_info()
            view = self.view_builder.build_view_from_cache({})
            flash = self._flash(
                "Still missing GeoLite2-City.mmdb. Copy it to the data folder and try again.",
                self.FLASH_LONG_S,
            )
            return snap, {}, status_cache.to_store(), view, flash

        self.my_location = self._resolve_my_location()

        status_cache.clear()
        empty_cache: dict[str, Any] = {}
        view = self.view_builder.build_view_from_cache(empty_cache)

        snap = self.model.snapshot()
        if isinstance(snap, dict):
            snap["app_info"] = self._build_app_info()

        flash = self._flash("Databases loaded. Geolocation enabled.", self.FLASH_LONG_S)
        return snap, empty_cache, status_cache.to_store(), view, flash

    def _handle_clear_cache(self, status_cache: StatusCache) -> tuple[Any, Any, Any, Any, Any]:
        snap = self.model.snapshot()
        if isinstance(snap, dict):
            snap["app_info"] = self._build_app_info()

        status_cache.clear()
        empty_cache: dict[str, Any] = {}
        view = self.view_builder.build_view_from_cache(empty_cache)
        flash = self._flash("Clearing cache...", self.FLASH_SHORT_S)
        return snap, empty_cache, status_cache.to_store(), view, flash

    def _handle_cache_terminal(
        self, status_cache: StatusCache, ui_cache: dict[str, Any]
    ) -> tuple[Any, Any, Any, Any, Any]:
        status_cache.log_cache(ui_cache, title="UI CACHE")
        flash = self._flash("Cache shown in terminal.", self.FLASH_SHORT_S)
        return no_update, no_update, no_update, no_update, flash

    def _handle_normal_poll(
        self, tick_n: int, status_cache: StatusCache, ui_cache: dict[str, Any]
    ) -> tuple[Any, Any, Any, Any, Any]:
        snap = self.model.snapshot()
        if not isinstance(snap, dict):
            view = self.view_builder.build_view_from_cache(ui_cache)
            flash = self._flash("Model snapshot is invalid. See terminal.", self.FLASH_LONG_S)
            return {"error": True}, ui_cache, status_cache.to_store(), view, flash

        snap["app_info"] = self._build_app_info()

        if snap.get("error"):
            view = self.view_builder.build_view_from_cache(ui_cache)
            return snap, ui_cache, status_cache.to_store(), view, no_update

        candidates_any = snap.get("map_candidates")
        candidates = candidates_any if isinstance(candidates_any, list) else []
        updated_cache = self.view_builder.merge_map_candidates(ui_cache, candidates)

        items_any = snap.get("cache_items")
        items = items_any if isinstance(items_any, list) else []
        status_cache.update(items)

        if self.DEBUG_COORDS and (tick_n % self.DEBUG_COORDS_EVERY_N_TICKS == 0):
            self.view_builder.debug_coords(updated_cache)

        view = self.view_builder.build_view_from_cache(updated_cache)
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
            "menu_help",
            "menu_about",
            self.SCR_MISSING_GEO_DB,
        }:
            return "modal-body mx-sticky-title"
        return "modal-body"

    @staticmethod
    def _toggle_on(value: Any) -> bool:
        return isinstance(value, list) and "on" in value

    @staticmethod
    def _is_geo_enabled(snapshot: Any) -> bool:
        if not isinstance(snapshot, dict):
            return False
        app_info = snapshot.get("app_info")
        if not isinstance(app_info, dict):
            return False
        return bool(app_info.get("geoinfo_enabled"))

    def _render_modal(
        self,
        modal_state: dict[str, Any] | None,
        snapshot: Any,
        ui_view: Any,
        geo_path: str,
    ) -> tuple[list[Any], str]:
        if not isinstance(modal_state, dict):
            return [], "modal-body"

        screen = modal_state.get("screen")
        payload = self._ensure_dict(modal_state.get("payload"))

        if not isinstance(screen, str) or not screen:
            return [], "modal-body"

        if screen == self.SCR_MISSING_GEO_DB:
            children = self._as_children(self.modal_text.missing_geo_db(geo_path))
            return children, self._class_for_modal_screen(screen)

        if screen == "map_click":
            click_data = payload.get("click_data")
            body = self.modal_text.for_click(click_data, ui_view)
            if body is None:
                return [], "modal-body"
            return self._as_children(body), "modal-body"

        if screen in self.MENU_SCREENS:
            show_system = bool(payload.get("show_system", False))
            body = self.modal_text.for_action(
                screen,
                snapshot=snapshot,
                show_system=show_system,
            )
            return self._as_children(body), self._class_for_modal_screen(screen)

        return [], "modal-body"

    def _register_callbacks(self) -> None:
        @self.app.callback(
            Output("key_action", "data"),
            Output("key_capture", "value"),
            Input("key_capture", "value"),
            prevent_initial_call=True,
        )
        def on_key(value: str) -> tuple[Any, str]:
            if not value:
                return no_update, ""

            token = value.split("|", 1)[0]
            key_map = {
                "__u__": "menu_unmapped",
                "__l__": "menu_lan_local",
                "__o__": "menu_open_ports",
                "__t__": "menu_cache_terminal",
                "__c__": "menu_clear",
                "__r__": "menu_recheck_geo",
                "__h__": "menu_help",
                "__a__": "menu_about",
                "__esc__": "escape",
            }

            action = key_map.get(token)
            if not action:
                return no_update, ""
            return {"action": action, "t": datetime.now().isoformat()}, ""

        @self.app.callback(
            Output("model_snapshot", "data"),
            Output("ui_cache", "data"),
            Output("status_cache", "data"),
            Output("ui_view", "data"),
            Output("status_flash", "data"),
            Output("ui_event_seen", "data"),
            Input("tick_status", "n_intervals"),
            Input("ui_event", "data"),
            Input("key_action", "data"),
            Input("menu_clear", "n_clicks"),
            Input("menu_cache_terminal", "n_clicks"),
            State("ui_cache", "data"),
            State("status_cache", "data"),
            State("ui_event_seen", "data"),
            prevent_initial_call=False,
        )
        def poll_model(
            tick_n: int,
            ui_event: Any,
            key_action: Any,
            _clear_clicks: int,
            _cache_terminal_clicks: int,
            ui_cache_data: Any,
            status_cache_data: Any,
            event_seen: Any,
        ):
            status_cache = StatusCache.from_store(status_cache_data)
            ui_cache = self._ensure_dict(ui_cache_data)

            sig = self._event_signature(ui_event)
            if sig and sig != event_seen and isinstance(ui_event, dict):
                if ui_event.get("type") == self.EVT_GEO_RECHECK:
                    snap, cache, sc_store, view, flash = self._handle_geo_recheck(status_cache)
                    return snap, cache, sc_store, view, flash, sig
                return no_update, no_update, no_update, no_update, no_update, sig

            trigger = ctx.triggered_id

            if trigger == "key_action" and isinstance(key_action, dict):
                action = key_action.get("action")

                if action == "menu_clear":
                    snap, cache, sc_store, view, flash = self._handle_clear_cache(status_cache)
                    return snap, cache, sc_store, view, flash, event_seen

                if action == "menu_cache_terminal":
                    a, b, c, d, flash = self._handle_cache_terminal(status_cache, ui_cache)
                    return a, b, c, d, flash, event_seen

            if trigger == "menu_clear":
                snap, cache, sc_store, view, flash = self._handle_clear_cache(status_cache)
                return snap, cache, sc_store, view, flash, event_seen

            if trigger == "menu_cache_terminal":
                a, b, c, d, flash = self._handle_cache_terminal(status_cache, ui_cache)
                return a, b, c, d, flash, event_seen

            snap, cache, sc_store, view, flash = self._handle_normal_poll(
                tick_n, status_cache, ui_cache
            )
            return snap, cache, sc_store, view, flash, event_seen

        @self.app.callback(
            Output("map", "figure"),
            Input("ui_view", "data"),
        )
        def render_map(ui_view: Any) -> Any:
            view = self._ensure_dict(ui_view)
            points = self._ensure_list(view.get("points"))
            summaries = self._ensure_dict(view.get("summaries"))
            return self.ui.create_figure((points, self.my_location), summaries=summaries)

        @self.app.callback(
            Output("status_bar", "children"),
            Input("model_snapshot", "data"),
            Input("status_cache", "data"),
            Input("status_flash", "data"),
            Input("ui_view", "data"),
            Input("tick_ui", "n_intervals"),
        )
        def render_status(
            snapshot: Any,
            status_cache_data: Any,
            status_flash: Any,
            ui_view: Any,
            _tick_ui: int,
        ) -> str:
            if isinstance(status_flash, dict):
                message = status_flash.get("message")
                until = status_flash.get("until")
                if (
                    isinstance(message, str)
                    and message
                    and isinstance(until, (int, float))
                    and datetime.now().timestamp() < float(until)
                ):
                    return message

            status_cache = StatusCache.from_store(status_cache_data)
            cache_chain = status_cache.format_chain()

            live_tcp_total = 0
            live_tcp_established = 0
            live_tcp_listen = 0
            live_udp_remote = 0
            live_udp_bound = 0
            updated = "--:--:--"
            status = "WAIT"
            note = ""

            if isinstance(snapshot, dict):
                if snapshot.get("error"):
                    status = "ERROR"
                    note = " (see terminal)"
                else:
                    stats = snapshot.get("stats")
                    if isinstance(stats, dict):
                        online = bool(stats.get("online", True))
                        status = "OK" if online else "OFFLINE"
                        live_tcp_total = self._to_int(stats.get("live_tcp_total"))
                        live_tcp_established = self._to_int(stats.get("live_tcp_established"))
                        live_tcp_listen = self._to_int(stats.get("live_tcp_listen"))
                        live_udp_remote = self._to_int(stats.get("live_udp_remote"))
                        live_udp_bound = self._to_int(stats.get("live_udp_bound"))
                        updated = stats.get("updated") or updated

            myloc = self._myloc_label()
            return (
                f"STATUS: {status}{note} | "
                f"LIVE: TCP {live_tcp_total} EST {live_tcp_established} "
                f"LST {live_tcp_listen} UDP R {live_udp_remote} "
                f"B {live_udp_bound} | "
                f"CACHE: {cache_chain} | "
                f"UPDATED: {updated} | "
                f"MYLOC: {myloc}"
            )

        @self.app.callback(
            Output("menu_panel", "className"),
            Output("menu_overlay", "className"),
            Input("menu_open", "data"),
        )
        def show_hide_menu(is_open: Any) -> tuple[str, str]:
            open_flag = bool(is_open)
            return self._menu_panel_class(open_flag), self._menu_overlay_class(open_flag)

        @self.app.callback(
            Output("menu_open", "data"),
            Input("btn_menu", "n_clicks"),
            Input("menu_overlay", "n_clicks"),
            Input("key_action", "data"),
            Input("menu_open_ports", "n_clicks"),
            Input("menu_unmapped", "n_clicks"),
            Input("menu_lan_local", "n_clicks"),
            Input("menu_cache_terminal", "n_clicks"),
            Input("menu_about", "n_clicks"),
            Input("menu_help", "n_clicks"),
            Input("menu_clear", "n_clicks"),
            Input("menu_recheck_geo", "n_clicks"),
            State("menu_open", "data"),
            prevent_initial_call=True,
        )
        def menu_controller(
            _btn: int,
            _overlay: int,
            key_action: Any,
            _open_ports: int,
            _unmapped: int,
            _lan_local: int,
            _cache_terminal: int,
            _info: int,
            _help: int,
            _clear: int,
            _recheck: int,
            menu_open: Any,
        ) -> Any:
            trigger = ctx.triggered_id

            if trigger == "btn_menu":
                return not bool(menu_open)
            if trigger == "menu_overlay":
                return False

            if (
                trigger == "key_action"
                and isinstance(key_action, dict)
                and key_action.get("action") == "escape"
                and bool(menu_open)
            ):
                return False

            if trigger in (self.MENU_SCREENS | self.MENU_COMMANDS):
                return False

            return no_update

        @self.app.callback(
            Output("modal_state", "data"),
            Output("ui_event", "data"),
            Output("modal_overlay", "className"),
            Output("modal_body", "children"),
            Output("modal_body", "className"),
            Input("tick_status", "n_intervals"),
            Input("menu_open_ports", "n_clicks"),
            Input("menu_unmapped", "n_clicks"),
            Input("menu_lan_local", "n_clicks"),
            Input("menu_about", "n_clicks"),
            Input("menu_help", "n_clicks"),
            Input("menu_recheck_geo", "n_clicks"),
            Input("toggle_open_ports_system", "value", allow_optional=True),
            Input("map", "clickData"),
            Input("btn_open_data", "n_clicks", allow_optional=True),
            Input("btn_check_databases", "n_clicks", allow_optional=True),
            Input("btn_close", "n_clicks"),
            Input("key_action", "data"),
            State("modal_state", "data"),
            State("model_snapshot", "data"),
            State("ui_view", "data"),
            State("open_ports_prefs", "data"),
            prevent_initial_call=True,
        )
        def modal_controller(
            _tick_n: int,
            _open_ports_clicks: int,
            _unmapped_clicks: int,
            _lan_local_clicks: int,
            _about_clicks: int,
            _help_clicks: int,
            _recheck_clicks: int,
            toggle_system_value: Any,
            click_data: Any,
            open_data_clicks: int | None,
            check_db_clicks: int | None,
            _close_clicks: int,
            key_action: Any,
            modal_state_data: Any,
            snapshot: Any,
            ui_view: Any,
            open_ports_prefs_data: Any,
        ):
            trigger = ctx.triggered_id
            geo_path = str(self.ctx.geo_data_dir)

            current_state = modal_state_data if isinstance(modal_state_data, dict) else None
            is_open = current_state is not None

            def make_state(screen: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
                return {"screen": screen, "t": datetime.now().isoformat(), "payload": payload or {}}

            show_system = self._toggle_on(toggle_system_value)

            if (
                is_open
                and isinstance(current_state, dict)
                and current_state.get("screen") == self.SCR_MISSING_GEO_DB
                and self._is_geo_enabled(snapshot)
            ):
                new_state = None
                children, class_name = self._render_modal(
                    new_state, snapshot, ui_view, geo_path
                )
                overlay_class = self._modal_overlay_class(False)
                return new_state, None, overlay_class, children, class_name

            if trigger == "btn_close":
                new_state = None
                children, class_name = self._render_modal(
                    new_state, snapshot, ui_view, geo_path
                )
                return (
                    new_state,
                    None,
                    self._modal_overlay_class(False),
                    children,
                    class_name,
                )

            if trigger == "key_action" and isinstance(key_action, dict):
                action = key_action.get("action")

                if action == "escape":
                    if is_open:
                        new_state = None
                        children, class_name = self._render_modal(
                            new_state, snapshot, ui_view, geo_path
                        )
                        return (
                            new_state,
                            None,
                            self._modal_overlay_class(False),
                            children,
                            class_name,
                        )
                    return no_update, None, no_update, no_update, no_update

                if not isinstance(action, str) or not action:
                    return no_update, None, no_update, no_update, no_update

                if action in self.MENU_COMMANDS:
                    if action == "menu_recheck_geo":
                        return (
                            no_update,
                            {"type": self.EVT_GEO_RECHECK, "t": datetime.now().isoformat()},
                            no_update,
                            no_update,
                            no_update,
                        )
                    return no_update, None, no_update, no_update, no_update

                if action in self.MENU_SCREENS:
                    new_state = make_state(action)
                    children, class_name = self._render_modal(
                        new_state, snapshot, ui_view, geo_path
                    )
                    return (
                        new_state,
                        None,
                        self._modal_overlay_class(True),
                        children,
                        class_name,
                    )

                return no_update, None, no_update, no_update, no_update

            if trigger == "btn_open_data":
                if isinstance(open_data_clicks, int) and open_data_clicks >= 1:
                    open_folder(Path(geo_path))
                return no_update, None, no_update, no_update, no_update

            if trigger == "btn_check_databases":
                if isinstance(check_db_clicks, int) and check_db_clicks >= 1:
                    return (
                        no_update,
                        {"type": self.EVT_GEO_RECHECK, "t": datetime.now().isoformat()},
                        no_update,
                        no_update,
                        no_update,
                    )
                return no_update, None, no_update, no_update, no_update

            if trigger == "toggle_open_ports_system":
                if (
                    not is_open
                    or not isinstance(current_state, dict)
                    or current_state.get("screen") != "menu_open_ports"
                ):
                    return no_update, None, no_update, no_update, no_update

                new_state = make_state(
                    "menu_open_ports", {"show_system": show_system}
                )
                children, class_name = self._render_modal(
                    new_state, snapshot, ui_view, geo_path
                )
                return (
                    new_state,
                    None,
                    self._modal_overlay_class(True),
                    children,
                    class_name,
                )

            if trigger in (
                self.MENU_SCREENS | self.MENU_COMMANDS
            ) and trigger not in self.MENU_COMMANDS:
                screen = str(trigger)
                payload: dict[str, Any] = {}

                if screen == "menu_open_ports":
                    prefs = (
                        open_ports_prefs_data
                        if isinstance(open_ports_prefs_data, dict)
                        else {}
                    )
                    payload["show_system"] = bool(
                        prefs.get("show_system", False)
                    )

                new_state = make_state(screen, payload)
                children, class_name = self._render_modal(
                    new_state, snapshot, ui_view, geo_path
                )
                return (
                    new_state,
                    None,
                    self._modal_overlay_class(True),
                    children,
                    class_name,
                )

            if trigger == "menu_recheck_geo":
                return (
                    no_update,
                    {"type": self.EVT_GEO_RECHECK, "t": datetime.now().isoformat()},
                    no_update,
                    no_update,
                    no_update,
                )

            if trigger == "map":
                if click_data is None:
                    return no_update, None, no_update, no_update, no_update
                new_state = make_state("map_click", {"click_data": click_data})
                children, class_name = self._render_modal(
                    new_state, snapshot, ui_view, geo_path
                )
                return (
                    new_state,
                    None,
                    self._modal_overlay_class(True),
                    children,
                    class_name,
                )

            return no_update, None, no_update, no_update, no_update
        
        @self.app.callback(
            Output("open_ports_prefs", "data"),
            Input("toggle_open_ports_system", "value", allow_optional=True),
            State("open_ports_prefs", "data"),
            prevent_initial_call=True,
        )
        def open_ports_toggle(toggle_value: Any, prefs_data: Any):
            prefs = prefs_data if isinstance(prefs_data, dict) else {}
            prefs["show_system"] = isinstance(toggle_value, list) and "on" in toggle_value
            return prefs

    def run(self) -> None:
        """Start the Dash server and launch the local UI."""
        host = "127.0.0.1"
        port = 8050
        url = f"http://{host}:{port}/"
        self._open_browser(url)

        self.app.run(
            host=host,
            port=port,
            debug=self.DASH_DEBUG,
            use_reloader=False,
        )

    def close(self) -> None:
        """Close model resources."""
        close_fn = getattr(self.model.geoinfo, "close", None)
        if callable(close_fn):
            close_fn()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG if TapMap.DEBUG_COORDS else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    runtime_ctx = build_runtime(APP_META)
    app = TapMap(runtime_ctx)
    try:
        app.run()
    finally:
        app.close()