"""About view rendering for the TapMap UI.

Build the About modal content from application
metadata and cached runtime information.
"""

from __future__ import annotations

from typing import Any

from dash import html

from .tables import kv_table


def render_about(
    *,
    app_name: str,
    app_version: str,
    app_author: str,
    snapshot: Any | None = None,
    is_docker: bool,
) -> list[Any]:
    """Render About view content.

    Read snapshot["app_info"] only and avoid network calls.
    """
    app_info: dict[str, Any] = {}
    if isinstance(snapshot, dict):
        info = snapshot.get("app_info")
        if isinstance(info, dict):
            app_info = info

    server_host_val = app_info.get("server_host")
    server_host = server_host_val if isinstance(server_host_val, str) else "-"
    server_port = app_info.get("server_port")
    poll_ms = app_info.get("poll_interval_ms")
    coord_precision = app_info.get("coord_precision")
    near_km = app_info.get("zoom_near_km")

    geoinfo_enabled = bool(app_info.get("geoinfo_enabled", False))
    geo_data_dir_val = app_info.get("geo_data_dir")
    geo_data_dir = geo_data_dir_val if isinstance(geo_data_dir_val, str) else ""

    myloc_mode_val = app_info.get("myloc_mode")
    myloc_mode = myloc_mode_val if isinstance(myloc_mode_val, str) else "OFF"
    my_location = app_info.get("my_location")

    public_ip_cached = app_info.get("public_ip_cached")
    public_ip_cached = (
        public_ip_cached if isinstance(public_ip_cached, str) and public_ip_cached else None
    )

    auto_geo_cached = app_info.get("auto_geo_cached")
    auto_geo = auto_geo_cached if isinstance(auto_geo_cached, dict) else {}

    os_text = app_info.get("os") if isinstance(app_info.get("os"), str) else "-"
    py_text = app_info.get("python") if isinstance(app_info.get("python"), str) else "-"

    net_backend_val = app_info.get("net_backend")
    net_backend = net_backend_val if isinstance(net_backend_val, str) else "-"
    net_backend_version_val = app_info.get("net_backend_version")
    net_backend_version = (
        net_backend_version_val if isinstance(net_backend_version_val, str) else "-"
    )

    tapmap_rows: list[tuple[str, str]] = [
        ("Name", app_name),
        ("Version", app_version),
        ("Author", app_author),
        ("Server port", str(server_port) if isinstance(server_port, int) else "-"),
        ("Poll interval", f"{poll_ms} ms" if isinstance(poll_ms, int) else "-"),
        ("Coord precision", str(coord_precision) if coord_precision is not None else "-"),
        ("Near distance", f"{near_km} km" if isinstance(near_km, (int, float)) else "-"),
    ]

    geo_rows: list[tuple[str, str]] = [
        ("Geolocation", "Enabled" if geoinfo_enabled else "Disabled"),
        ("GeoIP data folder", geo_data_dir if geo_data_dir else "-"),
    ]

    location_rows = _build_location_rows(
        myloc_mode=myloc_mode,
        my_location=my_location,
        public_ip_cached=public_ip_cached,
        auto_geo=auto_geo,
    )

    runtime_rows: list[tuple[str, str]] = [
        ("OS", os_text),
        ("Python", py_text),
        ("Network backend", net_backend),
        ("Backend version", net_backend_version),
        ("Server host", server_host),
        ("Docker", "Yes" if is_docker else "No"),
    ]

    return [
        html.H1(f"About {app_name}"),
        html.P(
            "TapMap inspects local socket data, enriches IP addresses "
            "with geolocation, and visualizes their locations on an interactive map."
        ),
        html.P(
            "It reads active socket data using a platform-specific backend, "
            "local MaxMind GeoLite2 databases for geolocation, "
            "and Dash with Plotly for visualization."
        ),
        html.P("All processing is local. TapMap does not inspect traffic contents."),
        kv_table(tapmap_rows),
        html.H2("Command line"),
        html.Ul(
            [
                html.Li([html.Code("tapmap"), " starts the application."]),
                html.Li([html.Code("tapmap --help"), " shows available command-line options."]),
                html.Li(
                    [
                        html.Code("tapmap --version"),
                        " and ",
                        html.Code("tapmap -v"),
                        " show installed version.",
                    ]
                ),
            ]
        ),
        html.H2("Geolocation"),
        html.P(
            "Geolocation is based on local MaxMind GeoLite2 .mmdb databases. "
            "The databases are not included."
        ),
        kv_table(geo_rows),
        html.Div(
            className="mx-path-row",
            children=[
                html.Pre(geo_data_dir, className="mx-path-box") if geo_data_dir else None,
                *(
                    []
                    if is_docker
                    else [
                        html.Button(
                            "Open data folder",
                            id="btn_open_data",
                            n_clicks=0,
                            className="mx-btn mx-btn--primary mx-btn--nowrap",
                            type="button",
                        )
                    ]
                ),
                html.Button(
                    "Recheck GeoIP databases",
                    id="btn_check_databases",
                    n_clicks=0,
                    className="mx-btn mx-btn--primary mx-btn--nowrap",
                    type="button",
                ),
            ],
        ),
        *(
            [
                html.P(
                    "Running in Docker. Place the GeoLite2 .mmdb files in the "
                    "host folder mounted to this path.",
                    className="mx-note",
                )
            ]
            if is_docker
            else []
        ),
        html.H2("Location"),
        kv_table(location_rows),
        html.H2("Runtime"),
        kv_table(runtime_rows),
        html.H2("Project"),
        html.P("TapMap is free and open source."),
        html.Ul(
            [
                html.Li(
                    html.A(
                        "Project page on GitHub",
                        href="https://github.com/olalie/tapmap",
                        target="_blank",
                        rel="noopener noreferrer",
                    )
                ),
                html.Li(
                    html.A(
                        "MaxMind GeoLite2 project",
                        href="https://dev.maxmind.com/geoip/geolite2-free-geolocation-data",
                        target="_blank",
                        rel="noopener noreferrer",
                    )
                ),
                html.Li(
                    html.A(
                        "Buy Me a Coffee",
                        href="https://www.buymeacoffee.com/olalie",
                        target="_blank",
                        rel="noopener noreferrer",
                    )
                ),
            ]
        ),
    ]


def _build_location_rows(
    *,
    myloc_mode: str,
    my_location: Any,
    public_ip_cached: str | None,
    auto_geo: dict[str, Any],
) -> list[tuple[str, str]]:
    """Build Location section rows for MY_LOCATION mode."""
    if myloc_mode == "OFF":
        return [("MY_LOCATION", "none (local marker hidden)")]

    if myloc_mode == "FIXED":
        if isinstance(my_location, (list, tuple)) and len(my_location) == 2:
            lon, lat = my_location[0], my_location[1]
            return [("MY_LOCATION", _fmt_coord(lon, lat))]
        return [("MY_LOCATION", "fixed (invalid value)")]

    rows: list[tuple[str, str]] = [("MY_LOCATION", "auto")]
    rows.append(("Public IP", public_ip_cached or "-"))

    if myloc_mode == "AUTO":
        place = _fmt_place(auto_geo.get("city"), auto_geo.get("country"))
        coord = _fmt_coord(auto_geo.get("lon"), auto_geo.get("lat"))
        rows.append(("AUTO place", place))
        rows.append(("AUTO coordinate", coord))
        return rows

    rows.append(("AUTO geo", "not available"))
    return rows


def _fmt_coord(lon: Any, lat: Any) -> str:
    """Format lon/lat coordinates for UI display."""
    if isinstance(lon, (int, float)) and isinstance(lat, (int, float)):
        return f"{float(lon)}, {float(lat)}"
    return "-"


def _fmt_place(city: Any, country: Any) -> str:
    """Format city/country place for UI display."""
    c = city.strip() if isinstance(city, str) else ""
    k = country.strip() if isinstance(country, str) else ""
    if c and k:
        return f"{c}, {k}"
    if k:
        return k
    return "-"
