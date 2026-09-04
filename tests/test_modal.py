"""Tests for modal state transition logic."""

from tapmap.state.modal import (
    ModalRoute,
    _decide_close,
    _decide_internal_navigation,
    _decide_map_click,
    _decide_row_click,
    _decide_screen_change,
    decide_modal_route,
)


def test_decide_close_closes_modal_from_close_button() -> None:
    """Close the modal when the close button is pressed."""
    result = _decide_close(
        trigger="btn_close",
        is_open=True,
        action=None,
    )

    assert result is None


def test_decide_close_closes_modal_from_escape_key() -> None:
    """Close the modal when Escape is pressed."""
    result = _decide_close(
        trigger="key_action",
        is_open=True,
        action="escape",
    )

    assert result is None


def test_decide_close_returns_sentinel_when_no_close_rule_matches() -> None:
    """Return the sentinel when no close rule matches."""
    result = _decide_close(
        trigger="something_else",
        is_open=True,
        action=None,
    )

    assert result is ...


def test_decide_screen_change_opens_modal_from_keyboard_action() -> None:
    """Open a modal screen from a keyboard action."""
    result = _decide_screen_change(
        trigger="key_action",
        is_open=False,
        current_screen=None,
        show_system=False,
        action="menu_about",
        menu_screens={"menu_about", "menu_open_ports"},
        open_ports_prefs=None,
        now_iso="2026-03-10T10:00:00",
    )

    assert result == {
        "screen": "menu_about",
        "t": "2026-03-10T10:00:00",
        "payload": {},
    }


def test_decide_screen_change_uses_open_ports_prefs_for_keyboard_open() -> None:
    """Include Open Ports preferences when opening that screen from keyboard input."""
    result = _decide_screen_change(
        trigger="key_action",
        is_open=False,
        current_screen=None,
        show_system=False,
        action="menu_open_ports",
        menu_screens={"menu_about", "menu_open_ports"},
        open_ports_prefs={"show_system": True},
        now_iso="2026-03-10T10:00:00",
    )

    assert result == {
        "screen": "menu_open_ports",
        "t": "2026-03-10T10:00:00",
        "payload": {"show_system": True},
    }


def test_decide_screen_change_updates_open_ports_payload_when_toggle_changes() -> None:
    """Update Open Ports payload when the toggle changes on the active screen."""
    result = _decide_screen_change(
        trigger="toggle_open_ports_system",
        is_open=True,
        current_screen="menu_open_ports",
        show_system=True,
        action=None,
        menu_screens={"menu_about", "menu_open_ports"},
        open_ports_prefs=None,
        now_iso="2026-03-10T10:00:00",
    )

    assert result == {
        "screen": "menu_open_ports",
        "t": "2026-03-10T10:00:00",
        "payload": {"show_system": True},
    }


def test_decide_screen_change_returns_none_for_toggle_outside_open_ports_screen() -> None:
    """Ignore the Open Ports toggle outside the matching active screen."""
    result = _decide_screen_change(
        trigger="toggle_open_ports_system",
        is_open=True,
        current_screen="menu_about",
        show_system=True,
        action=None,
        menu_screens={"menu_about", "menu_open_ports"},
        open_ports_prefs=None,
        now_iso="2026-03-10T10:00:00",
    )

    assert result is None


def test_decide_screen_change_opens_modal_from_menu_click() -> None:
    """Open a modal screen from a menu click."""
    result = _decide_screen_change(
        trigger="menu_about",
        is_open=False,
        current_screen=None,
        show_system=False,
        action=None,
        menu_screens={"menu_about", "menu_open_ports"},
        open_ports_prefs=None,
        now_iso="2026-03-10T10:00:00",
    )

    assert result == {
        "screen": "menu_about",
        "t": "2026-03-10T10:00:00",
        "payload": {},
    }


def test_decide_screen_change_ignores_dict_shaped_triggers() -> None:
    """A dict-shaped (pattern-matching) trigger does not crash the plain-string screen check."""
    trigger = {
        "type": "sc_row",
        "timestamp": "x",
        "pid": 1,
        "ip": "1.1.1.1",
        "port": 1,
        "proto": "tcp",
    }
    result = _decide_screen_change(
        trigger=trigger,
        is_open=True,
        current_screen="menu_significant_connections",
        show_system=False,
        action=None,
        menu_screens={"menu_significant_connections"},
        open_ports_prefs=None,
        now_iso="2026-03-10T10:00:00",
    )

    assert result is None


def test_decide_internal_navigation_returns_to_significant_connections_list() -> None:
    """The Significant Connection detail Back button returns to the history list screen."""
    result = _decide_internal_navigation(
        trigger="btn_sc_back",
        now_iso="2026-03-10T10:00:00",
    )

    assert result == {
        "screen": "menu_significant_connections",
        "t": "2026-03-10T10:00:00",
        "payload": {},
    }


def test_decide_row_click_returns_none_for_non_row_trigger() -> None:
    """Ignore triggers that aren't a Significant Connections row click."""
    result = _decide_row_click(
        trigger="menu_about",
        now_iso="2026-03-10T10:00:00",
    )

    assert result is None


def test_decide_row_click_returns_modal_state_for_a_row_click() -> None:
    """Open the Significant Connection detail screen with the clicked row's identity fields."""
    trigger = {
        "type": "sc_row",
        "timestamp": "2026-08-23T18:42:16.013313",
        "pid": 7920,
        "ip": "8.8.8.8",
        "port": 443,
        "proto": "tcp",
    }

    result = _decide_row_click(
        trigger=trigger,
        now_iso="2026-03-10T10:00:00",
    )

    assert result == {
        "screen": "menu_significant_connection_detail",
        "t": "2026-03-10T10:00:00",
        "payload": {
            "timestamp": "2026-08-23T18:42:16.013313",
            "pid": 7920,
            "ip": "8.8.8.8",
            "port": 443,
            "proto": "tcp",
        },
    }


def test_decide_map_click_returns_none_for_non_map_trigger() -> None:
    """Ignore non-map triggers."""
    result = _decide_map_click(
        trigger="menu_about",
        click_data={"point": 1},
        now_iso="2026-03-10T10:00:00",
    )

    assert result is None


def test_decide_map_click_returns_none_when_click_data_is_missing() -> None:
    """Ignore map triggers without click data."""
    result = _decide_map_click(
        trigger="map",
        click_data=None,
        now_iso="2026-03-10T10:00:00",
    )

    assert result is None


def test_decide_map_click_returns_modal_state_for_map_click() -> None:
    """Open the map click screen when click data is present."""
    click_data = {"points": [{"customdata": "x"}]}

    result = _decide_map_click(
        trigger="map",
        click_data=click_data,
        now_iso="2026-03-10T10:00:00",
    )

    assert result == {
        "screen": "map_click",
        "t": "2026-03-10T10:00:00",
        "payload": {"click_data": click_data},
    }


def test_decide_modal_route_applies_close_when_close_rule_matches() -> None:
    """Return an apply route with None modal state for closing."""
    result = decide_modal_route(
        trigger="btn_close",
        is_open=True,
        current_screen="menu_about",
        action=None,
        show_system=False,
        menu_screens={"menu_about", "menu_open_ports"},
        open_ports_prefs=None,
        click_data=None,
        now_iso="2026-03-10T10:00:00",
    )

    assert result == ModalRoute(action="apply", modal_state=None)


def test_decide_modal_route_applies_screen_change_when_menu_screen_is_selected() -> None:
    """Return an apply route for a screen transition."""
    result = decide_modal_route(
        trigger="menu_about",
        is_open=False,
        current_screen=None,
        action=None,
        show_system=False,
        menu_screens={"menu_about", "menu_open_ports"},
        open_ports_prefs=None,
        click_data=None,
        now_iso="2026-03-10T10:00:00",
    )

    assert result == ModalRoute(
        action="apply",
        modal_state={
            "screen": "menu_about",
            "t": "2026-03-10T10:00:00",
            "payload": {},
        },
    )

def test_decide_modal_route_applies_map_click_after_higher_priority_checks() -> None:
    """Return an apply route for a map click when higher priority rules do not match."""
    click_data = {"points": [{"customdata": "x"}]}

    result = decide_modal_route(
        trigger="map",
        is_open=False,
        current_screen=None,
        action=None,
        show_system=False,
        menu_screens={"menu_about", "menu_open_ports"},
        open_ports_prefs=None,
        click_data=click_data,
        now_iso="2026-03-10T10:00:00",
    )

    assert result == ModalRoute(
        action="apply",
        modal_state={
            "screen": "map_click",
            "t": "2026-03-10T10:00:00",
            "payload": {"click_data": click_data},
        },
    )


def test_decide_modal_route_applies_row_click_after_higher_priority_checks() -> None:
    """Return an apply route for a Significant Connections row click."""
    trigger = {
        "type": "sc_row",
        "timestamp": "2026-08-23T18:42:16.013313",
        "pid": 7920,
        "ip": "8.8.8.8",
        "port": 443,
        "proto": "tcp",
    }

    result = decide_modal_route(
        trigger=trigger,
        is_open=True,
        current_screen="menu_significant_connections",
        action=None,
        show_system=False,
        menu_screens={"menu_significant_connections"},
        open_ports_prefs=None,
        click_data=None,
        now_iso="2026-03-10T10:00:00",
    )

    assert result == ModalRoute(
        action="apply",
        modal_state={
            "screen": "menu_significant_connection_detail",
            "t": "2026-03-10T10:00:00",
            "payload": {
                "timestamp": "2026-08-23T18:42:16.013313",
                "pid": 7920,
                "ip": "8.8.8.8",
                "port": 443,
                "proto": "tcp",
            },
        },
    )


def test_decide_modal_route_returns_noop_when_no_rule_matches() -> None:
    """Return noop when no route rule matches."""
    result = decide_modal_route(
        trigger="something_else",
        is_open=False,
        current_screen=None,
        action=None,
        show_system=False,
        menu_screens={"menu_about", "menu_open_ports"},
        open_ports_prefs=None,
        click_data=None,
        now_iso="2026-03-10T10:00:00",
    )

    assert result == ModalRoute(action="noop")
