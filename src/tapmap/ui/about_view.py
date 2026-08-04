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

    Read snapshot["runtime_info"] only and avoid network calls.
    """
    runtime_info: dict[str, Any] = {}
    if isinstance(snapshot, dict):
        info = snapshot.get("runtime_info")
        if isinstance(info, dict):
            runtime_info = info

    server_host_val = runtime_info.get("server_host")
    server_host = server_host_val if isinstance(server_host_val, str) else "-"
    server_port = runtime_info.get("server_port")
    poll_ms = runtime_info.get("poll_interval_ms")
    coord_precision = runtime_info.get("coord_precision")
    near_km = runtime_info.get("zoom_near_km")
    launch_browser = bool(runtime_info.get("launch_browser", True))

    cache_retention_min = runtime_info.get("cache_retention_min")
    if not isinstance(cache_retention_min, int):
        cache_retention_min = 0

    geoinfo_enabled = bool(runtime_info.get("geoinfo_enabled", False))
    geo_provider = str(runtime_info.get("geo_provider") or "-")
    geo_database_date = str(runtime_info.get("geo_database_date") or "-")

    provider_label = {
        "maxmind": "MaxMind GeoLite2",
        "dbip": "DB-IP Lite",
        "none": "None",
    }.get(geo_provider, geo_provider)

    myloc_mode_val = runtime_info.get("myloc_mode")
    myloc_mode = myloc_mode_val if isinstance(myloc_mode_val, str) else "OFF"
    my_location = runtime_info.get("my_location")

    public_ip_cached = runtime_info.get("public_ip_cached")
    public_ip_cached = (
        public_ip_cached if isinstance(public_ip_cached, str) and public_ip_cached else None
    )

    auto_geo_cached = runtime_info.get("auto_geo_cached")
    auto_geo = auto_geo_cached if isinstance(auto_geo_cached, dict) else {}

    os_text = runtime_info.get("os") if isinstance(runtime_info.get("os"), str) else "-"
    py_text = runtime_info.get("python") if isinstance(runtime_info.get("python"), str) else "-"

    net_backend_val = runtime_info.get("net_backend")
    net_backend = net_backend_val if isinstance(net_backend_val, str) else "-"
    net_backend_version_val = runtime_info.get("net_backend_version")
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
        ("Databases", provider_label),
        ("Database date", geo_database_date if geo_database_date else "-"),
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
        ("Browser launch", "Enabled" if launch_browser else "Disabled"),
        (
            "Cache retention",
            "Until Clear cache"
            if cache_retention_min == 0
            else f"{cache_retention_min} min",
        ),
    ]

    return [
        html.H1(f"About {app_name}"),
        html.P(
            "TapMap inspects local socket activity, enriches IP addresses with "
            "geolocation, visualizes connections on an interactive map, and "
            "builds insights from the most recent 30 days of activity."
        ),
        html.P(
            "Historical insights include recurring activity patterns, provider "
            "distribution, country activity and generated activity logs."
        ),
        html.P(
            "It reads active socket data using a platform-specific backend, "
            "local GeoIP databases for geolocation, "
            "and Dash with Plotly for visualization."
        ),
        html.P("Runs locally. No telemetry. TapMap does not inspect traffic contents."),
        kv_table(tapmap_rows),
        html.H2("Command line"),
        html.Pre(
            "tapmap            Start application\n"
            "tapmap --help     Show options\n"
            "tapmap --version  Show version"
        ),
        html.H2("Geolocation"),
        html.P(
            "Geolocation uses locally installed MaxMind GeoLite2 or DB-IP Lite .mmdb databases."
        ),
        kv_table(geo_rows),
        html.P(
            [
                "IP Geolocation by ",
                html.A(
                    "DB-IP",
                    href="https://db-ip.com",
                    target="_blank",
                    rel="noopener noreferrer",
                ),
            ]
        ) if geo_provider == "dbip" else None,
        html.P(
            [
                "This product includes GeoLite Data created by MaxMind, available from ",
                html.A(
                    "https://www.maxmind.com",
                    href="https://www.maxmind.com",
                    target="_blank",
                    rel="noopener noreferrer",
                ),
                ".",
            ]
        ) if geo_provider == "maxmind" else None,
        html.H2("Location"),
        kv_table(location_rows),
        html.H2("Runtime"),
        kv_table(runtime_rows),
        html.H2("Project"),
        html.P("TapMap is free and open source, "
               "developed by Ola Lie at TIP Teknologi i Praksis AS."),
        html.Ul(
            [
                html.Li(
                    html.A(
                        "GitHub repository",
                        href="https://github.com/olalie/tapmap",
                        target="_blank",
                        rel="noopener noreferrer",
                    )
                ),
                html.Li(
                    html.A(
                        "Docker Hub image",
                        href="https://hub.docker.com/r/olalie/tapmap",
                        target="_blank",
                        rel="noopener noreferrer",
                    )
                ),
                html.Li(
                    html.A(
                        "Professional services",
                        href="https://tip.no",
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

    if myloc_mode == "ENV":
        if isinstance(my_location, (list, tuple)) and len(my_location) == 2:
            lon, lat = my_location[0], my_location[1]
            return [
                ("MY_LOCATION", "env override"),
                ("Coordinate", _fmt_coord(lon, lat)),
            ]
        return [("MY_LOCATION", "env override")]

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
