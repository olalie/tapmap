"""Significant Connections history view rendering for the TapMap UI.

Build the Significant Connections history table from the persisted,
oldest-first SignificantConnections.items event list.
"""

from __future__ import annotations

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
    """Build modal content for the Significant Connections history.

    items is SignificantConnections.items (oldest first, unchanged); display
    order is newest first, computed here for presentation only.
    """
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
        ]
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
    """Build the narrow, headingless verification-status bullet cell.

    Uses the raw persisted app_verification_status, not
    display_verification_status()'s live-view pending substitution: a
    persisted event's status is either a terminal value or was never
    resolved at capture time, and history has no notion of "still
    resolving" for a past event - a None status is presented as Unknown,
    consistent with how any other unresolved status already displays.
    """
    status = event.get("app_verification_status")
    glyph = html.Span(
        "■",
        className="mx-cell-text",
        style={"color": verification_status_color(status)},
        title=verification_status_label(status),
    )
    return html.Td(glyph)
