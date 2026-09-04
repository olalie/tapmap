"""Test Significant Connections history and detail rendering."""

from __future__ import annotations

from typing import Any

from dash import html

from tapmap.ui.significant_connections_view import (
    render_significant_connection_detail,
    render_significant_connections,
)


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
    """Render items and return the history table."""
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


def _detail_value(children: list[Any], section: str, label: str) -> Any:
    """Return the rendered value for a label in a detail section."""
    section_index = next(
        i for i, c in enumerate(children) if isinstance(c, html.H2) and c.children == section
    )
    table = children[section_index + 1]
    tbody = next(c for c in table.children if isinstance(c, html.Tbody))
    for row in tbody.children:
        key_td, value_td = row.children
        if key_td.children == label:
            return value_td.children
    raise AssertionError(f"label {label!r} not found in section {section!r}")


def test_render_significant_connections_empty_history_shows_placeholder() -> None:
    """An empty history renders a placeholder, not a table."""
    result = render_significant_connections([])

    assert isinstance(result[1], html.Pre)
    assert "no significant connections" in result[1].children.lower()


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


def test_network_operator_and_application_show_persisted_values() -> None:
    """Network operator and Application cells show asn_org and app_name verbatim."""
    table = _table([_event(asn_org="Google LLC", app_name="Chrome")])
    cells = _rows(table)[0].children

    assert _cell_text(cells[3]) == "Google LLC"
    assert _cell_text(cells[4]) == "Chrome"


def test_reason_cell_tooltip_shows_the_complete_value() -> None:
    """A truncated Reason cell exposes its full value on hover, via cell()'s Span tooltip."""
    all_reasons = ["new_app", "new_country", "new_provider", "new_port", "verification_failed"]
    table = _table([_event(reasons=all_reasons)])

    reason_span = _rows(table)[0].children[1].children

    assert reason_span.title == (
        "New application, New country, New network operator, New port, Verification failed"
    )


def test_verification_bullet_renders_glyph_color_and_tooltip_for_a_resolved_status() -> None:
    """The verification cell shows only the colored glyph, with the status label as its tooltip."""
    table = _table([_event(app_verification_status="verified")])

    span = _verification_span(_rows(table)[0].children[5])

    assert span.children == "■"
    assert span.style["color"] == "#00ff66"
    assert span.title == "Verified"


def test_verification_bullet_shows_unknown_not_pending_for_a_null_persisted_status() -> None:
    """Verify that a missing persisted verification status shows Unknown, not Pending."""
    table = _table([_event(app_verification_status=None, exe="/opt/firefox.exe")])

    span = _verification_span(_rows(table)[0].children[5])

    assert span.style["color"] == "#ffff00"
    assert span.title == "Unknown"


def test_render_significant_connection_detail_shows_values_from_every_section() -> None:
    """The detail view renders representative values from each of its five sections."""
    event = _event(
        timestamp="2026-08-23T18:42:16.013313",
        reasons=["new_app", "new_country"],
        lat=52.37,
        lon=4.89,
        asn=13335,
        asn_org="Cloudflare, Inc.",
        city="Amsterdam",
        country="The Netherlands",
        country_code="NL",
        app_name="Firefox",
        app_creator="Mozilla Corporation",
        app_verification_status="verified",
        ip="2606:4700:4403::ac40:94eb",
        port=443,
        proto="tcp",
        process_name="firefox.exe",
        pid=7920,
        exe="C:\\Program Files\\Mozilla Firefox\\firefox.exe",
    )

    children = render_significant_connection_detail(event)

    assert _detail_value(children, "Event", "Timestamp").children == "2026-08-23 18:42:16"
    assert _detail_value(children, "Event", "Reason").children == "New application, New country"
    assert (
        _detail_value(children, "Location", "Location").children
        == "🇳🇱 Amsterdam, The Netherlands"
    )
    assert _detail_value(children, "Location", "Coordinates").children == "Lat 52.37, Lon 4.89"
    assert _detail_value(children, "Application", "Application").children == "Firefox"
    assert "Verified" in _detail_value(children, "Application", "Verification").children
    assert (
        _detail_value(children, "Connection", "Remote IP").children
        == "2606:4700:4403::ac40:94eb"
    )
    assert _detail_value(children, "Connection", "Protocol").children == "TCP"
    assert (
        _detail_value(children, "Process", "Executable").children
        == "C:\\Program Files\\Mozilla Firefox\\firefox.exe"
    )


def test_render_significant_connection_detail_shows_dash_for_missing_values() -> None:
    """Coordinates/ASN/signature fields show '-' when absent; null verification shows Unknown."""
    event = _event(
        lat=None,
        lon=None,
        asn=None,
        app_verification_status=None,
        app_signature_state=None,
        app_signature_state_details=None,
    )

    children = render_significant_connection_detail(event)

    assert _detail_value(children, "Location", "Coordinates").children == "-"
    assert _detail_value(children, "Location", "ASN").children == "-"
    assert _detail_value(children, "Application", "Signature state").children == "-"
    assert _detail_value(children, "Application", "Signature details").children == "-"
    assert "Unknown" in _detail_value(children, "Application", "Verification").children
