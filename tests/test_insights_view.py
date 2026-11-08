"""Test Insights panel and entry detail rendering."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any
from unittest.mock import patch

from dash import html

from tapmap.state.insights import EntryHistory
from tapmap.ui.insights_view import render_insights_entry_detail, render_insights_panel

_TODAY = date(2026, 10, 23).toordinal()


def _walk(component: Any) -> Iterator[Any]:
    """Yield component and all nested children."""
    if isinstance(component, (list, tuple)):
        for child in component:
            yield from _walk(child)
        return
    yield component
    children = getattr(component, "children", None)
    if children is not None and not isinstance(children, str):
        yield from _walk(children)


def _entry_rows(children: list[Any]) -> list[Any]:
    """Return rows carrying an Insights entry ID."""
    return [
        c
        for c in _walk(children)
        if isinstance(getattr(c, "id", None), dict) and c.id.get("type") == "insights-entry"
    ]


def _panel_data() -> dict[str, Any]:
    """Return Insights panel data covering all four categories."""
    return {
        "top": {
            "applications": [{"value": "Firefox"}],
            "providers": [{"value": "Example Networks"}],
            "countries": [{"value": "NO", "name": "Norway"}, {"value": "SE", "name": "Sweden"}],
            "ports": [{"value": "443"}],
        }
    }


def _kv_rows(children: list[Any]) -> dict[str, Any]:
    """Return detail table rows as {label: value}."""
    rows: dict[str, Any] = {}
    for c in _walk(children):
        if isinstance(c, html.Tr):
            key, value = c.children
            rows[key.children] = value.children
    return rows


def _history(**overrides: Any) -> EntryHistory:
    """Return an EntryHistory with activity today and 4 days ago."""
    history = EntryHistory(
        last_seen_day=_TODAY,
        first_seen_day=_TODAY - 4,
        active_days=2,
        days=[False] * 25 + [True, False, False, False, True],
    )
    history.update(overrides)  # type: ignore[typeddict-item]
    return history


def test_panel_has_no_today_section() -> None:
    """The panel renders only the Top 5+ section."""
    children = render_insights_panel(_panel_data())

    titles = [
        c.children for c in _walk(children) if getattr(c, "className", None) == "insights-title"
    ]
    assert titles == ["Top 5+"]
    assert not any(
        isinstance(c, html.Div) and isinstance(c.children, str) and c.children.startswith("[NEW")
        for c in _walk(children)
    )


def test_panel_rows_in_all_categories_are_clickable_entries() -> None:
    """Every row carries an insights-entry ID with its category and value."""
    rows = _entry_rows(render_insights_panel(_panel_data()))

    assert [(r.id["category"], r.id["value"]) for r in rows] == [
        ("applications", "Firefox"),
        ("providers", "Example Networks"),
        ("countries", "NO"),
        ("countries", "SE"),
        ("ports", "443"),
    ]
    assert all("clickable" in r.className for r in rows)


def test_panel_marks_only_selected_country_as_selected() -> None:
    """Only the row of the selected country has the selected class."""
    rows = _entry_rows(render_insights_panel(_panel_data(), selected_country="NO"))

    selected = [r.id["value"] for r in rows if "selected" in r.className.split()]
    assert selected == ["NO"]


def test_panel_does_not_select_non_country_with_matching_value() -> None:
    """A non-country value equal to the selected country is not marked selected."""
    data = {"top": {"applications": [{"value": "NO"}]}}
    rows = _entry_rows(render_insights_panel(data, selected_country="NO"))

    assert "selected" not in rows[0].className.split()


def test_detail_shows_history_values_and_strip() -> None:
    """The detail view shows last seen, earliest recorded, active days, and a dated strip."""
    children = render_insights_entry_detail("applications", "Firefox", _history(), _TODAY)

    assert children[0].children == "Firefox"
    assert children[1].children == "Application"
    rows = _kv_rows(children)
    assert rows["Last seen"] == "Today"
    assert rows["Earliest recorded (last 30 days)"] == "2026-10-19"
    assert rows["Active days"] == "2 of the last 30 days"
    start_label, strip, end_label = rows["Activity"].children
    assert start_label.children == "Sep 24"
    assert end_label.children == "Oct 23"
    assert len(strip.children) == 30
    assert [s.className for s in strip.children[-5:]] == [
        "rpt-day--on",
        "rpt-day--off",
        "rpt-day--off",
        "rpt-day--off",
        "rpt-day--on",
    ]


def test_detail_shows_yesterday_for_last_seen() -> None:
    """Last seen one day ago is shown as Yesterday."""
    children = render_insights_entry_detail(
        "ports", "443", _history(last_seen_day=_TODAY - 1), _TODAY
    )

    assert _kv_rows(children)["Last seen"] == "Yesterday"
    assert children[1].children == "Port"


def test_detail_shows_date_for_earliest_recorded_on_first_window_day() -> None:
    """Activity on the first day of the window is shown as that date."""
    children = render_insights_entry_detail(
        "providers",
        "Example Networks",
        _history(first_seen_day=_TODAY - 29),
        _TODAY,
    )

    assert _kv_rows(children)["Earliest recorded (last 30 days)"] == "2026-09-24"
    assert children[1].children == "Network operator"


def test_detail_title_for_country_uses_flag_and_name() -> None:
    """A country entry is titled with its flag and name."""
    with patch("tapmap.ui.insights_view.country_name", return_value="Norway"):
        children = render_insights_entry_detail("countries", "NO", _history(), _TODAY)

    assert children[0].children == "\U0001f1f3\U0001f1f4 Norway"
    assert children[1].children == "Country"


def test_detail_shows_unavailable_message_without_history() -> None:
    """Show an unavailable message instead of history values when history is None."""
    children = render_insights_entry_detail("applications", "Firefox", None, _TODAY)

    assert any(isinstance(c, html.Pre) and "no longer available" in c.children for c in children)
    assert _kv_rows(children) == {}
