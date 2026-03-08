"""Dash layout construction for the TapMap UI.

Build the top level application layout and reusable
UI elements used by the controller.
"""

from __future__ import annotations

from typing import Any

from dash import dcc, html


def render_layout(
    *,
    app_name: str,
    start_fig: Any,
    graph_config: dict[str, Any],
    poll_interval_ms: int,
    status_cache_store: dict[str, Any],
    initial_modal_state: dict[str, Any] | None,
    initial_modal_open: bool,
    initial_body_children: list[Any],
    initial_body_class: str,
    menu_overlay_class: str,
    menu_panel_class: str,
    modal_overlay_class: str,
) -> html.Div:
    """Render the application layout."""
    return html.Div(
        className="app",
        children=[
            dcc.Store(id="menu_open", data=False),
            dcc.Store(id="key_action", data=None),
            dcc.Store(id="status_flash", data=None),
            dcc.Store(id="model_snapshot", data=None),
            dcc.Store(id="ui_cache", data={}),
            dcc.Store(id="status_cache", data=status_cache_store),
            dcc.Store(id="ui_view", data={"points": [], "summaries": {}, "details": {}}),
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
            dcc.Interval(id="tick_model", interval=poll_interval_ms, n_intervals=0),
            dcc.Graph(
                id="map",
                figure=start_fig,
                className="map",
                config=graph_config,
                clear_on_unhover=True,
            ),
            html.Div(app_name, className="app-title"),
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
                className=menu_overlay_class,
            ),
            html.Nav(
                id="menu_panel",
                className=menu_panel_class,
                children=[
                    html.Div("Actions", className="mx-panel__title"),
                    html.Div(
                        [
                            _menu_button("Show unmapped public services (U)", "menu_unmapped"),
                            _menu_button(
                                "Show established LAN/LOCAL services (L)", "menu_lan_local"
                            ),
                            _menu_button("Show open ports (O)", "menu_open_ports"),
                            _menu_button("Show cache in terminal (T)", "menu_cache_terminal"),
                            _menu_button("Clear cache (C)", "menu_clear_cache"),
                        ],
                        className="mx-menu-group",
                    ),
                    html.Div(
                        [
                            _menu_button("Recheck GeoIP databases (R)", "menu_recheck_geoip"),
                            _menu_button("Help (H)", "menu_help"),
                            _menu_button("About (A)", "menu_about"),
                        ],
                        className="mx-menu-group",
                    ),
                ],
            ),
            html.Div(
                id="modal_overlay",
                className=modal_overlay_class,
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


def _menu_button(label: str, btn_id: str) -> html.Button:
    """Render a menu button."""
    return html.Button(
        label,
        id=btn_id,
        n_clicks=0,
        className="mx-btn mx-btn--menu",
        type="button",
    )
