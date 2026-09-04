"""Render Significant Connections history and details."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from dash import html

from .formatting import (
    country_flag,
    safe_str,
    verification_status_color,
    verification_status_label,
)
from .tables import ColumnSpec, build_table, cell

_REASON_LABELS = {
    "new_app": "New application",
    "new_country": "New country",
    "new_provider": "New network operator",
    "new_port": "New port",
    "verification_failed": "Verification failed",
}

_COLUMNS = [
    ColumnSpec("Timestamp", "20%"),
    ColumnSpec("Reason", "21%"),
    ColumnSpec("Location", "20%"),
    ColumnSpec("Network operator", "20%"),
    ColumnSpec("Application", "15%"),
    ColumnSpec("", "4%"),
]


def render_significant_connections(items: list[dict[str, Any]]) -> list[Any]:
    """Render Significant Connections history with newest events first."""
    header = html.H1("Significant connections", className="mx-h1")

    if not items:
        return [header, html.Pre("(no significant connections)")]

    table = build_table(
        class_name="mx-table mx-significant-connections",
        columns=_COLUMNS,
        header_cells=[c.header for c in _COLUMNS],
        body_rows=[_build_row(event) for event in _sorted_newest_first(items)],
    )

    return [header, table]


def _sorted_newest_first(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return items newest first by timestamp; equal timestamps keep their existing order."""
    return sorted(items, key=lambda event: safe_str(event.get("timestamp")), reverse=True)


def _build_row(event: dict[str, Any]) -> html.Tr:
    """Build one history row from a persisted Significant Connection event."""
    return html.Tr(
        [
            cell(_format_timestamp(event.get("timestamp"))),
            cell(_format_reasons(event.get("reasons"))),
            cell(_format_location(event)),
            cell(safe_str(event.get("asn_org"))),
            cell(safe_str(event.get("app_name"))),
            _verification_cell(event),
        ],
        id={
            "type": "sc_row",
            "timestamp": event.get("timestamp"),
            "pid": event.get("pid"),
            "ip": event.get("ip"),
            "port": event.get("port"),
            "proto": event.get("proto"),
        },
        n_clicks=0,
    )


def _format_timestamp(timestamp: Any) -> str:
    """Format a persisted ISO timestamp for display, to the second."""
    if not isinstance(timestamp, str) or not timestamp:
        return ""
    try:
        return datetime.fromisoformat(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return timestamp


def _format_reasons(reasons: Any) -> str:
    """Join an event's significance reasons into one comma-separated, user-facing line."""
    values = reasons if isinstance(reasons, list) else []
    return ", ".join(_REASON_LABELS.get(r, safe_str(r)) for r in values)


def _format_location(event: dict[str, Any]) -> str:
    """Format an event's Location cell: flag-or-globe plus city/country, per TapMap convention."""
    city = safe_str(event.get("city"))
    country = safe_str(event.get("country"))
    place = ", ".join(part for part in (city, country) if part)
    return f"{country_flag(event.get('country_code'))} {place or 'Unknown place name'}"


def _verification_cell(event: dict[str, Any]) -> html.Td:
    """Build the verification status cell, showing a missing status as Unknown."""
    status = event.get("app_verification_status")
    glyph = html.Span(
        "■",
        className="mx-cell-text",
        style={"color": verification_status_color(status)},
        title=verification_status_label(status),
    )
    return html.Td(glyph)


def render_significant_connection_detail(event: dict[str, Any]) -> list[Any]:
    """Build modal content for one Significant Connection's detail view."""
    return [
        html.Button(
            "← Significant connections",
            id="btn_sc_back",
            n_clicks=0,
            className="mx-btn mx-btn--nowrap",
            type="button",
        ),
        html.H1("Significant Connection", className="mx-h1"),
        html.H2("Event"),
        _detail_table(
            [
                ("Timestamp", _format_timestamp(event.get("timestamp"))),
                ("Reason", _format_reasons(event.get("reasons"))),
            ]
        ),
        html.H2("Location"),
        _detail_table(
            [
                ("Location", _format_location(event)),
                ("Coordinates", _format_coordinates(event.get("lat"), event.get("lon"))),
                ("Network operator", safe_str(event.get("asn_org"))),
                ("ASN", safe_str(event.get("asn")) or "-"),
            ]
        ),
        html.H2("Application"),
        _detail_table(
            [
                ("Application", safe_str(event.get("app_name"))),
                ("Creator", safe_str(event.get("app_creator"))),
                ("Verification", _verification_value(event)),
                ("Signature state", safe_str(event.get("app_signature_state")) or "-"),
                (
                    "Signature details",
                    safe_str(event.get("app_signature_state_details")) or "-",
                ),
            ]
        ),
        html.H2("Connection"),
        _detail_table(
            [
                ("Remote IP", safe_str(event.get("ip"))),
                ("Port", safe_str(event.get("port"))),
                ("Service", safe_str(event.get("service"))),
                ("Protocol", safe_str(event.get("proto")).upper()),
            ]
        ),
        html.H2("Process"),
        _detail_table(
            [
                ("Process", safe_str(event.get("process_name"))),
                ("PID", safe_str(event.get("pid"))),
                ("Executable", safe_str(event.get("exe"))),
            ]
        ),
    ]


def _format_coordinates(lat: Any, lon: Any) -> str:
    """Format latitude/longitude as 'Lat <value>, Lon <value>', or '-' if either is missing."""
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return "-"
    return f"Lat {lat}, Lon {lon}"


def _verification_value(event: dict[str, Any]) -> html.Span:
    """Build the Verification detail row's value: colored bullet plus visible status label."""
    status = event.get("app_verification_status")
    return html.Span(
        [
            html.Span("■ ", style={"color": verification_status_color(status)}),
            verification_status_label(status),
        ]
    )


def _detail_table(rows: Iterable[tuple[str, Any]]) -> html.Table:
    """Build a two-column detail table with wrapping text and component values."""
    body: list[Any] = []
    for key, value in rows:
        if isinstance(value, str) or value is None:
            v = value or ""
            value_cell = html.Span(v, title=v if v else None)
        else:
            value_cell = value
        body.append(html.Tr([html.Td(key), html.Td(value_cell)]))

    colgroup = html.Colgroup([html.Col(style={"width": "180px"}), html.Col()])

    return html.Table(className="mx-table mx-kv", children=[colgroup, html.Tbody(body)])
