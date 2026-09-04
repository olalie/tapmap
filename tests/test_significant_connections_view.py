"""Test the Significant Connections history table rendering."""

from __future__ import annotations

from typing import Any

from dash import html

from tapmap.ui.significant_connections_view import render_significant_connections


def _event(**overrides: Any) -> dict[str, Any]:
    """Return a minimal persisted Significant Connection event."""
    event = {
        "timestamp": "2026-08-23T18:42:16.013313",
        "reasons": ["new_app"],
        "pid": 7920,
        "proto": "tcp",
        "ip": "2606:4700:4403::ac40:94eb",
        "port": 443,
        "service": "https",
        "lat": None,
        "lon": None,
        "process_name": "firefox.exe",
        "exe": "/opt/firefox.exe",
        "city": "Amsterdam",
        "country": "The Netherlands",
        "country_code": "NL",
        "asn": 13335,
        "asn_org": "Cloudflare, Inc.",
        "app_name": "Firefox",
        "app_creator": "Mozilla Corporation",
        "app_verification_status": "verified",
        "app_signature_state": "SignedAndTrusted",
        "app_signature_state_details": None,
    }
    event.update(overrides)
    return event


def _table(items: list[dict[str, Any]]) -> html.Table:
    """Render items and return the table component (fails if the empty state rendered instead)."""
    result = render_significant_connections(items)
    table = result[1]
    assert isinstance(table, html.Table)
    return table


def _headers(table: html.Table) -> list[str]:
    """Return the header text for each column."""
    thead = next(c for c in table.children if isinstance(c, html.Thead))
    return [th.children for th in thead.children.children]


def _rows(table: html.Table) -> list[html.Tr]:
    """Return the body rows from a rendered table component."""
    tbody = next(c for c in table.children if isinstance(c, html.Tbody))
    return tbody.children


def _cell_text(td: html.Td) -> str:
    """Return the visible text of one rendered table cell."""
    return td.children.children


def _verification_span(td: html.Td) -> html.Span:
    """Return the verification bullet's Span component from its cell."""
    return td.children


# --- empty state ---


def test_render_significant_connections_empty_history_shows_placeholder() -> None:
    """An empty history renders a placeholder, not a table."""
    result = render_significant_connections([])

    assert isinstance(result[1], html.Pre)
    assert "no significant connections" in result[1].children.lower()


# --- table structure ---


def test_table_headers_match_the_required_columns() -> None:
    """Headers are the five named columns, then an unlabeled verification-status column."""
    table = _table([_event()])

    assert _headers(table) == [
        "Timestamp",
        "Reason",
        "Location",
        "Network operator",
        "Application",
        "",
    ]


def test_one_row_per_persisted_event() -> None:
    """Each persisted event produces exactly one row."""
    table = _table([_event(ip="1.1.1.1"), _event(ip="2.2.2.2"), _event(ip="3.3.3.3")])

    assert len(_rows(table)) == 3


# --- ordering ---


def test_events_are_displayed_newest_first() -> None:
    """Rows are sorted by timestamp descending."""
    older = _event(timestamp="2026-08-23T18:00:00.000000", ip="1.1.1.1")
    newer = _event(timestamp="2026-08-23T19:00:00.000000", ip="2.2.2.2")

    table = _table([older, newer])
    rows = _rows(table)

    assert _cell_text(rows[0].children[0]) == "2026-08-23 19:00:00"
    assert _cell_text(rows[1].children[0]) == "2026-08-23 18:00:00"


def test_equal_timestamps_preserve_existing_relative_order() -> None:
    """Same-timestamp events keep their original (oldest-first) relative order after reversal."""
    same_ts = "2026-08-23T18:42:16.013313"
    first_appended = _event(timestamp=same_ts, ip="1.1.1.1", app_name="First")
    second_appended = _event(timestamp=same_ts, ip="2.2.2.2", app_name="Second")

    table = _table([first_appended, second_appended])
    rows = _rows(table)

    assert _cell_text(rows[0].children[4]) == "First"
    assert _cell_text(rows[1].children[4]) == "Second"


# --- reason labels ---


def test_single_reason_shows_its_user_facing_label() -> None:
    """A single reason renders its display label, not the raw identifier."""
    table = _table([_event(reasons=["new_country"])])

    assert _cell_text(_rows(table)[0].children[1]) == "New country"


def test_multiple_reasons_join_into_one_cell_on_one_line() -> None:
    """All of an event's reasons appear in the same cell, comma-separated."""
    all_reasons = ["new_app", "new_country", "new_provider", "new_port", "verification_failed"]
    table = _table([_event(reasons=all_reasons)])

    assert _cell_text(_rows(table)[0].children[1]) == (
        "New application, New country, New network operator, New port, Verification failed"
    )


# --- location ---


def test_location_with_city_and_country_shows_flag_and_both() -> None:
    """City and country present: flag, city, comma, country."""
    table = _table([_event(country_code="NL", city="Amsterdam", country="The Netherlands")])

    assert _cell_text(_rows(table)[0].children[2]) == "🇳🇱 Amsterdam, The Netherlands"


def test_location_with_country_only_omits_the_comma() -> None:
    """Country present, city absent: flag and country, no dangling comma."""
    table = _table([_event(country_code="NL", city=None, country="The Netherlands")])

    assert _cell_text(_rows(table)[0].children[2]) == "🇳🇱 The Netherlands"


def test_location_with_city_only_shows_globe() -> None:
    """City present, country absent: globe fallback, city shown."""
    table = _table([_event(country_code=None, city="Amsterdam", country=None)])

    assert _cell_text(_rows(table)[0].children[2]) == "🌐 Amsterdam"


def test_location_with_neither_shows_globe_and_unknown_place_name() -> None:
    """Neither city nor country present: globe and 'Unknown place name'."""
    table = _table([_event(country_code=None, city=None, country=None)])

    assert _cell_text(_rows(table)[0].children[2]) == "🌐 Unknown place name"


# --- network operator / application ---


def test_network_operator_and_application_show_persisted_values() -> None:
    """Network operator and Application cells show asn_org and app_name verbatim."""
    table = _table([_event(asn_org="Google LLC", app_name="Chrome")])
    cells = _rows(table)[0].children

    assert _cell_text(cells[3]) == "Google LLC"
    assert _cell_text(cells[4]) == "Chrome"


# --- full-value hover tooltip ---


def test_reason_cell_tooltip_shows_the_complete_value() -> None:
    """A truncated Reason cell exposes its full value on hover, via cell()'s Span tooltip."""
    all_reasons = ["new_app", "new_country", "new_provider", "new_port", "verification_failed"]
    table = _table([_event(reasons=all_reasons)])

    reason_span = _rows(table)[0].children[1].children

    assert reason_span.title == (
        "New application, New country, New network operator, New port, Verification failed"
    )


def test_location_cell_tooltip_matches_displayed_value() -> None:
    """The Location cell's tooltip matches its displayed flag-and-place text."""
    table = _table([_event(country_code="NL", city="Amsterdam", country="The Netherlands")])

    location_span = _rows(table)[0].children[2].children

    assert location_span.title == "🇳🇱 Amsterdam, The Netherlands"


# --- verification bullet ---


def test_verification_bullet_shows_no_text_only_the_glyph() -> None:
    """The verification cell holds only the bullet glyph, no textual status."""
    table = _table([_event(app_verification_status="verified")])

    span = _verification_span(_rows(table)[0].children[5])

    assert span.children == "■"


def test_verification_bullet_uses_the_verified_color_and_tooltip() -> None:
    """A verified event's bullet is green with a 'Verified' tooltip."""
    table = _table([_event(app_verification_status="verified")])

    span = _verification_span(_rows(table)[0].children[5])

    assert span.style["color"] == "#00ff66"
    assert span.title == "Verified"


def test_verification_bullet_uses_the_failed_color_and_tooltip() -> None:
    """A failed event's bullet is red with a 'Failed' tooltip."""
    table = _table([_event(app_verification_status="failed")])

    span = _verification_span(_rows(table)[0].children[5])

    assert span.style["color"] == "#ff4444"
    assert span.title == "Failed"


def test_verification_bullet_uses_the_unknown_color_and_tooltip() -> None:
    """An unknown-status event's bullet is yellow with an 'Unknown' tooltip."""
    table = _table([_event(app_verification_status="unknown")])

    span = _verification_span(_rows(table)[0].children[5])

    assert span.style["color"] == "#ffff00"
    assert span.title == "Unknown"


def test_verification_bullet_shows_unknown_not_pending_for_a_null_persisted_status() -> None:
    """A persisted null status (exe present) shows yellow Unknown, not white Pending.

    Unlike the live cache's Pending/Retrieving substitution, a persisted
    Significant Connection event has no "still resolving" concept - a null
    status is presented the same way any other unresolved status would be.
    """
    table = _table([_event(app_verification_status=None, exe="/opt/firefox.exe")])

    span = _verification_span(_rows(table)[0].children[5])

    assert span.style["color"] == "#ffff00"
    assert span.title == "Unknown"


def test_verification_bullet_shows_unknown_for_a_null_status_with_no_exe() -> None:
    """A persisted null status with no exe also shows Unknown, same as with an exe."""
    table = _table([_event(app_verification_status=None, exe=None)])

    span = _verification_span(_rows(table)[0].children[5])

    assert span.style["color"] == "#ffff00"
    assert span.title == "Unknown"
