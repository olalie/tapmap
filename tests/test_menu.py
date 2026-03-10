"""Tests for menu open/close decision logic."""

from state.menu import compute_menu_open_state


def test_btn_menu_toggles_menu_open_state() -> None:
    """Toggle menu when menu button is pressed."""
    result = compute_menu_open_state(
        trigger="btn_menu",
        menu_open=True,
        key_action=None,
        menu_screens=set(),
        menu_commands=set(),
    )

    assert result is False


def test_menu_overlay_closes_menu() -> None:
    """Close menu when clicking the overlay."""
    result = compute_menu_open_state(
        trigger="menu_overlay",
        menu_open=True,
        key_action=None,
        menu_screens=set(),
        menu_commands=set(),
    )

    assert result is False


def test_escape_key_closes_menu_when_open() -> None:
    """Close menu when Escape is pressed and menu is open."""
    result = compute_menu_open_state(
        trigger="key_action",
        menu_open=True,
        key_action={"action": "escape"},
        menu_screens=set(),
        menu_commands=set(),
    )

    assert result is False


def test_escape_key_does_not_close_menu_when_already_closed() -> None:
    """Return None when Escape is pressed but menu is already closed."""
    result = compute_menu_open_state(
        trigger="key_action",
        menu_open=False,
        key_action={"action": "escape"},
        menu_screens=set(),
        menu_commands=set(),
    )

    assert result is None


def test_trigger_in_menu_screens_closes_menu() -> None:
    """Close menu when navigating to a menu screen."""
    result = compute_menu_open_state(
        trigger="settings",
        menu_open=True,
        key_action=None,
        menu_screens={"settings"},
        menu_commands=set(),
    )

    assert result is False


def test_trigger_in_menu_commands_closes_menu() -> None:
    """Close menu when executing a menu command."""
    result = compute_menu_open_state(
        trigger="refresh",
        menu_open=True,
        key_action=None,
        menu_screens=set(),
        menu_commands={"refresh"},
    )

    assert result is False


def test_unrelated_trigger_returns_none() -> None:
    """Return None when the trigger does not affect menu state."""
    result = compute_menu_open_state(
        trigger="something_else",
        menu_open=True,
        key_action=None,
        menu_screens=set(),
        menu_commands=set(),
    )

    assert result is None
