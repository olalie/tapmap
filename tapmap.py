from __future__ import annotations

import logging
import platform
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Final

import psutil
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update

from app_dirs import open_folder
from config import COORD_PRECISION, MY_LOCATION, POLL_INTERVAL_MS, ZOOM_NEAR_KM
from model.geoinfo import GeoInfo
from model.model import Model
from model.netinfo import NetInfo
from model.public_ip import iter_public_ip_candidates
from runtime import AppMeta, RuntimeContext, build_runtime
from ui.cache_view import CacheViewBuilder
from ui.map_ui import MapUI
from ui.modal_text import ModalTextBuilder
from ui.status_cache import StatusCache

LonLat = tuple[float, float]

APP_META: Final[AppMeta] = AppMeta(name="TapMap", version="v1.0", author="Ola Lie")


class TapMap:
    """Dash controller and UI wiring.

    Design goals:
      - Keep callbacks thin and readable.
      - Keep model state transitions in the polling callback.
      - Use a simple UI event store for one off actions.
      - Split modal logic into routing (state) and rendering (HTML).
    """

    # ---------------------------------------------------------------------
    # Menu configuration
    # ---------------------------------------------------------------------

    MENU_SCREENS: ClassVar[frozenset[str]] = frozenset(
        {"menu_help", "menu_about", "menu_open_ports", "menu_unmapped"}
    )
    MENU_COMMANDS: ClassVar[frozenset[str]] = frozenset(
        {"menu_clear", "menu_cache_terminal", "menu_recheck_geo"}
    )
    # ---------------------------------------------------------------------
    # Debug and runtime flags
    # ---------------------------------------------------------------------

    DASH_DEBUG = False
    DEBUG_COORDS = False
    DEBUG_COORDS_EVERY_N_TICKS = 6

    # ---------------------------------------------------------------------
    # Timing configuration
    # ---------------------------------------------------------------------

    # Polling intervals (milliseconds)
    MODEL_TICK_MS = 5000  # model polling (network, psutil, etc.)
    UI_TICK_MS = 500  # UI updates (status flash timeout)

    # Status flash durations (seconds)
    FLASH_SHORT_S = 1.5  # clear cache, show cache
    FLASH_LONG_S = 3.0  # geo recheck result

    # ---------------------------------------------------------------------
    # Event and modal identifiers
    # ---------------------------------------------------------------------

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
            coord_precision=COORD_PRECISION, debug=self.DEBUG_COORDS
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

    # ---------------------------------------------------------------------
    # Layout
    # ---------------------------------------------------------------------

    def _build_layout(self, start_fig: Any) -> html.Div:
        geo_ready = bool(getattr(self.model.geoinfo, "city_enabled", False))

        initial_modal_state: dict[str, Any] | None = None
        if not geo_ready:
            initial_modal_state = {
                "screen": self.SCR_MISSING_GEO_DB,
                "t": datetime.now().isoformat(),
                "payload": {"geo_data_dir": str(self.ctx.geo_data_dir)},
            }

        return html.Div(
            className="app",
            children=[
                dcc.Store(id="menu_open", data=False),
                dcc.Store(id="key_action", data=None),
                dcc.Store(id="status_flash", data=None),
                dcc.Store(id="model_snapshot", data=None),
                dcc.Store(id="ui_cache", data={}),
                dcc.Store(id="status_cache", data={}),
                dcc.Store(id="ui_view", data={"points": [], "summaries": {}, "details": {}}),
                dcc.Store(id="geo_data_dir_store", data=str(self.ctx.geo_data_dir)),
                dcc.Store(id="ui_event", data=None),
                dcc.Store(id="ui_event_seen", data=None),
                dcc.Store(id="modal_open", data=bool(initial_modal_state)),
                dcc.Store(id="modal_state", data=initial_modal_state),
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
                    "☰", id="btn_menu", n_clicks=0, className="mx-btn mx-btn--icon", type="button"
                ),
                html.Div(
                    id="menu_overlay", n_clicks=0, className="mx-overlay", style={"display": "none"}
                ),
                html.Nav(
                    id="menu_panel",
                    className="mx-panel",
                    style={"display": "none"},
                    children=[
                        html.Div("Actions", className="mx-panel__title"),
                        html.Div(
                            [
                                self._menu_button("Show unmapped endpoints (U)", "menu_unmapped"),
                                self._menu_button("Show open ports (O)", "menu_open_ports"),
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
                    className="modal-overlay",
                    style={"display": "none"},
                    children=[
                        html.Div(
                            className="modal-card",
                            children=[
                                html.Div(id="modal_body", className="modal-body", children=[]),
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
                        "STATUS: WAIT | LIVE: CON 0 EST 0 LST 0 | "
                        "CACHE: EST 0 - LOC 0 - NON_GEO 0 = GEO 0 -> RIP 0 -> RLOC 0 | "
                        "UPDATED: --:--:--"
                    ),
                ),
            ],
        )

    def _menu_button(self, label: str, btn_id: str) -> html.Button:
        return html.Button(
            label, id=btn_id, n_clicks=0, className="mx-btn mx-btn--menu", type="button"
        )

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

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

    # ---------------------------------------------------------------------
    # My location resolution
    # ---------------------------------------------------------------------

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

    # ---------------------------------------------------------------------
    # About payload
    # ---------------------------------------------------------------------

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
            "psutil": getattr(psutil, "__version__", "-"),
        }

    # ---------------------------------------------------------------------
    # Poll handlers
    # ---------------------------------------------------------------------

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

    # ---------------------------------------------------------------------
    # Browser open
    # ---------------------------------------------------------------------

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

    # ---------------------------------------------------------------------
    # Callbacks
    # ---------------------------------------------------------------------

    def _register_callbacks(self) -> None:
        # -----------------------------------------------------------------
        # Keyboard capture (keys.js writes tokens into #key_capture)
        # -----------------------------------------------------------------
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
                "__o__": "menu_open_ports",
                "__u__": "menu_unmapped",
                "__t__": "menu_cache_terminal",
                "__c__": "menu_clear",
                "__h__": "menu_help",
                "__a__": "menu_about",
                "__r__": "menu_recheck_geo",
                "__esc__": "escape",
            }

            action = key_map.get(token)
            if not action:
                return no_update, ""
            return {"action": action, "t": datetime.now().isoformat()}, ""

        # -----------------------------------------------------------------
        # Polling / state engine
        # -----------------------------------------------------------------
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

            # 1) One-off ui_event handling (dedupe)
            sig = self._event_signature(ui_event)
            if sig and sig != event_seen and isinstance(ui_event, dict):
                if ui_event.get("type") == self.EVT_GEO_RECHECK:
                    snap, cache, sc_store, view, flash = self._handle_geo_recheck(status_cache)
                    return snap, cache, sc_store, view, flash, sig

                # Unknown event: mark as seen so it won't re-run forever
                return no_update, no_update, no_update, no_update, no_update, sig

            trigger = ctx.triggered_id

            # 2) Keyboard commands handled here
            if trigger == "key_action" and isinstance(key_action, dict):
                action = key_action.get("action")

                if action == "menu_clear":
                    snap, cache, sc_store, view, flash = self._handle_clear_cache(status_cache)
                    return snap, cache, sc_store, view, flash, event_seen

                if action == "menu_cache_terminal":
                    a, b, c, d, flash = self._handle_cache_terminal(status_cache, ui_cache)
                    return a, b, c, d, flash, event_seen

            # 3) Menu commands handled here
            if trigger == "menu_clear":
                snap, cache, sc_store, view, flash = self._handle_clear_cache(status_cache)
                return snap, cache, sc_store, view, flash, event_seen

            if trigger == "menu_cache_terminal":
                a, b, c, d, flash = self._handle_cache_terminal(status_cache, ui_cache)
                return a, b, c, d, flash, event_seen

            # 4) Normal polling
            snap, cache, sc_store, view, flash = self._handle_normal_poll(
                tick_n, status_cache, ui_cache
            )
            return snap, cache, sc_store, view, flash, event_seen

        # -----------------------------------------------------------------
        # Map rendering
        # -----------------------------------------------------------------
        @self.app.callback(
            Output("map", "figure"),
            Input("ui_view", "data"),
        )
        def render_map(ui_view: Any) -> Any:
            view = self._ensure_dict(ui_view)
            points = self._ensure_list(view.get("points"))
            summaries = self._ensure_dict(view.get("summaries"))
            return self.ui.create_figure((points, self.my_location), summaries=summaries)

        # -----------------------------------------------------------------
        # Status rendering
        # -----------------------------------------------------------------
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

            view = self._ensure_dict(ui_view)
            points = self._ensure_list(view.get("points"))
            rloc_map = len(points)
            cache_chain = status_cache.format_chain(rloc_map=rloc_map)

            live_con = 0
            live_est = 0
            live_lst = 0
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
                        live_con = self._to_int(stats.get("live_con"))
                        live_est = self._to_int(stats.get("live_est"))
                        live_lst = self._to_int(stats.get("live_lst"))
                        updated = stats.get("updated") or updated

            myloc = self._myloc_label()
            return (
                f"STATUS: {status}{note} | "
                f"LIVE: CON {live_con} EST {live_est} LST {live_lst} | "
                f"CACHE: {cache_chain} | "
                f"UPDATED: {updated} | "
                f"MYLOC: {myloc}"
            )

        # -----------------------------------------------------------------
        # Menu panel visibility
        # -----------------------------------------------------------------
        @self.app.callback(
            Output("menu_panel", "style"),
            Output("menu_overlay", "style"),
            Input("menu_open", "data"),
        )
        def show_hide_menu(is_open: Any) -> tuple[dict[str, str], dict[str, str]]:
            display = "block" if bool(is_open) else "none"
            return {"display": display}, {"display": display}

        # -----------------------------------------------------------------
        # Modal overlay visibility
        # -----------------------------------------------------------------
        @self.app.callback(
            Output("modal_overlay", "style"),
            Input("modal_open", "data"),
            prevent_initial_call=False,
        )
        def show_hide_modal(modal_open: Any) -> dict[str, str]:
            return {"display": "flex"} if bool(modal_open) else {"display": "none"}

        # -----------------------------------------------------------------
        # Menu open/close controller
        # -----------------------------------------------------------------
        @self.app.callback(
            Output("menu_open", "data"),
            Input("btn_menu", "n_clicks"),
            Input("menu_overlay", "n_clicks"),
            Input("key_action", "data"),
            Input("menu_open_ports", "n_clicks"),
            Input("menu_unmapped", "n_clicks"),
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

        # -----------------------------------------------------------------
        # Modal routing (state machine + event emitter)
        # -----------------------------------------------------------------
        @self.app.callback(
            Output("modal_open", "data"),
            Output("modal_state", "data"),
            Output("ui_event", "data"),
            Input("tick_status", "n_intervals"),
            Input("menu_open_ports", "n_clicks"),
            Input("menu_unmapped", "n_clicks"),
            Input("menu_about", "n_clicks"),
            Input("menu_help", "n_clicks"),
            Input("menu_recheck_geo", "n_clicks"),
            Input("toggle_unmapped_lan_local", "value", allow_optional=True),
            Input("map", "clickData"),
            Input("btn_open_data", "n_clicks", allow_optional=True),
            Input("btn_check_databases", "n_clicks", allow_optional=True),
            Input("btn_close", "n_clicks"),
            Input("key_action", "data"),
            State("modal_open", "data"),
            State("modal_state", "data"),
            State("geo_data_dir_store", "data"),
            State("model_snapshot", "data"),
            prevent_initial_call=True,
        )
        def modal_router(
            _tick_n: int,
            _open_ports_clicks: int,
            _unmapped_clicks: int,
            _info_clicks: int,
            _help_clicks: int,
            _recheck_clicks: int,
            toggle_value: Any,
            click_data: Any,
            open_data_clicks: int | None,
            check_db_clicks: int | None,
            _close_clicks: int,
            key_action: Any,
            modal_open: Any,
            modal_state: Any,
            geo_data_dir: Any,
            snapshot: Any,
        ):
            """Route UI actions into modal state changes and one-off ui_event commands.

            Rules:
            - This callback is the only writer of modal_open and modal_state.
            - MENU_SCREENS open modals.
            - MENU_COMMANDS never open modals.
            - Recheck databases always emits ui_event and is handled by poll_model.
            - Auto-close missing geo modal when geolocation becomes enabled.
            - snapshot is State (not Input) to avoid dependency cycles.
            """
            trigger = ctx.triggered_id
            geo_path = str(geo_data_dir) if isinstance(geo_data_dir, str) else ""
            current_state = self._ensure_dict(modal_state)

            def make_state(screen: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
                return {"screen": screen, "t": datetime.now().isoformat(), "payload": payload or {}}

            def toggle_on(val: Any) -> bool:
                return isinstance(val, list) and "on" in val

            def is_geo_enabled(snap: Any) -> bool:
                if not isinstance(snap, dict):
                    return False
                app_info = snap.get("app_info")
                if not isinstance(app_info, dict):
                    return False
                return bool(app_info.get("geoinfo_enabled"))

            show_lan_local = toggle_on(toggle_value)

            # --------------------------------------------------------------
            # 0) Auto-close the missing DB modal when geo becomes enabled
            # --------------------------------------------------------------
            if (
                bool(modal_open)
                and current_state.get("screen") == self.SCR_MISSING_GEO_DB
                and is_geo_enabled(snapshot)
            ):
                return False, None, None

            # --------------------------------------------------------------
            # 1) Close modal button
            # --------------------------------------------------------------
            if trigger == "btn_close":
                return False, None, None

            # --------------------------------------------------------------
            # 2) Keyboard actions
            # --------------------------------------------------------------
            if trigger == "key_action" and isinstance(key_action, dict):
                action = key_action.get("action")

                if action == "escape":
                    # Close only if a modal is open.
                    if bool(modal_open):
                        return False, None, None
                    return no_update, no_update, None

                if not isinstance(action, str) or not action:
                    return no_update, no_update, None

                # Commands: do not open modal
                if action in self.MENU_COMMANDS:
                    if action == "menu_recheck_geo":
                        return (
                            no_update,
                            no_update,
                            {"type": self.EVT_GEO_RECHECK, "t": datetime.now().isoformat()},
                        )
                    # menu_clear and menu_cache_terminal are handled by poll_model directly.
                    return no_update, no_update, None

                # Screens: open modal
                if action in self.MENU_SCREENS:
                    payload: dict[str, Any] = {}
                    if action == "menu_unmapped":
                        payload["show_lan_local"] = show_lan_local
                    return True, make_state(action, payload), None

                return no_update, no_update, None

            # --------------------------------------------------------------
            # 3) Open data folder (button inside missing screen)
            # --------------------------------------------------------------
            if trigger == "btn_open_data":
                if not geo_path:
                    return no_update, no_update, None
                if not isinstance(open_data_clicks, int) or open_data_clicks < 1:
                    return no_update, no_update, None
                open_folder(Path(geo_path))
                return no_update, no_update, None

            # --------------------------------------------------------------
            # 4) Recheck databases button inside missing screen
            # --------------------------------------------------------------
            if trigger == "btn_check_databases":
                if not isinstance(check_db_clicks, int) or check_db_clicks < 1:
                    return no_update, no_update, None
                return (
                    no_update,
                    no_update,
                    {"type": self.EVT_GEO_RECHECK, "t": datetime.now().isoformat()},
                )

            # --------------------------------------------------------------
            # 5) Toggle inside unmapped modal
            # --------------------------------------------------------------
            if trigger == "toggle_unmapped_lan_local":
                if not bool(modal_open):
                    return no_update, no_update, None
                if current_state.get("screen") != "menu_unmapped":
                    return no_update, no_update, None
                return True, make_state("menu_unmapped", {"show_lan_local": show_lan_local}), None

            # --------------------------------------------------------------
            # 6) Menu screens that open modals
            # --------------------------------------------------------------
            if trigger in {"menu_open_ports", "menu_unmapped", "menu_help", "menu_about"}:
                screen = str(trigger)
                payload: dict[str, Any] = {}
                if screen == "menu_unmapped":
                    payload["show_lan_local"] = show_lan_local
                return True, make_state(screen, payload), None

            # --------------------------------------------------------------
            # 7) Menu command: recheck databases (no modal)
            # --------------------------------------------------------------
            if trigger == "menu_recheck_geo":
                return (
                    no_update,
                    no_update,
                    {"type": self.EVT_GEO_RECHECK, "t": datetime.now().isoformat()},
                )

            # --------------------------------------------------------------
            # 8) Map click opens click modal
            # --------------------------------------------------------------
            if trigger == "map":
                if click_data is None:
                    return no_update, no_update, None
                return True, make_state("map_click", {"click_data": click_data}), None

            return no_update, no_update, None

        # -----------------------------------------------------------------
        # Modal rendering (HTML only)
        # -----------------------------------------------------------------
        @self.app.callback(
            Output("modal_body", "children"),
            Output("modal_body", "className"),
            Input("modal_state", "data"),
            Input("model_snapshot", "data"),
            Input("ui_view", "data"),
            State("geo_data_dir_store", "data"),
        )
        def modal_renderer(modal_state: Any, snapshot: Any, ui_view: Any, geo_data_dir: Any):
            state = self._ensure_dict(modal_state)
            screen = state.get("screen")
            payload = self._ensure_dict(state.get("payload"))
            geo_path = str(geo_data_dir) if isinstance(geo_data_dir, str) else ""

            def as_children(value: Any) -> list[Any]:
                if value is None:
                    return []
                if isinstance(value, (list, tuple)):
                    return list(value)
                return [value]

            def class_for_screen(name: str | None) -> str:
                if name in {
                    "menu_help",
                    "menu_open_ports",
                    "menu_unmapped",
                    "menu_about",
                    self.SCR_MISSING_GEO_DB,
                }:
                    return "modal-body mx-sticky-title"
                return "modal-body"

            if not screen:
                return [], "modal-body"

            if screen == self.SCR_MISSING_GEO_DB:
                return as_children(self.modal_text.missing_geo_db(geo_path)), class_for_screen(
                    screen
                )

            if screen == "map_click":
                click_data = payload.get("click_data")
                body = self.modal_text.for_click(click_data, ui_view)
                if body is None:
                    return [], "modal-body"
                return as_children(body), "modal-body"

            if isinstance(screen, str) and screen in self.MENU_SCREENS:
                show_lan_local = bool(payload.get("show_lan_local", False))
                body = self.modal_text.for_action(
                    screen, snapshot=snapshot, show_lan_local=show_lan_local
                )
                return as_children(body), class_for_screen(screen)

            return [], "modal-body"

    # ---------------------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------------------

    def run(self) -> None:
        """Start the Dash server."""
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
        """Release resources held by the model."""
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
