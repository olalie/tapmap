"""Tests for poll decision logic."""

import state.poll as poll


def test_recheck_trigger_from_menu() -> None:
    """Return geo_recheck when recheck menu is clicked."""
    decision = poll.decide_poll_action(
        trigger="menu_recheck_geoip",
        key_action=None,
    )

    assert decision.action == poll.ACTION_GEO_RECHECK


def test_recheck_trigger_from_button() -> None:
    """Return geo_recheck when database check button is clicked."""
    decision = poll.decide_poll_action(
        trigger="btn_check_databases",
        key_action=None,
    )

    assert decision.action == poll.ACTION_GEO_RECHECK


def test_clear_cache_from_menu() -> None:
    """Return clear_cache when clear cache menu item is clicked."""
    decision = poll.decide_poll_action(
        trigger="menu_clear_cache",
        key_action=None,
    )

    assert decision.action == poll.ACTION_CLEAR_CACHE


def test_cache_terminal_from_menu() -> None:
    """Return cache_terminal when cache terminal menu item is clicked."""
    decision = poll.decide_poll_action(
        trigger="menu_cache_terminal",
        key_action=None,
    )

    assert decision.action == poll.ACTION_CACHE_TERMINAL


def test_recheck_from_keyboard_action() -> None:
    """Return geo_recheck when keyboard action requests GeoIP recheck."""
    decision = poll.decide_poll_action(
        trigger="key_action",
        key_action={"action": "menu_recheck_geoip"},
    )

    assert decision.action == poll.ACTION_GEO_RECHECK


def test_clear_cache_from_keyboard_action() -> None:
    """Return clear_cache when keyboard action requests cache clear."""
    decision = poll.decide_poll_action(
        trigger="key_action",
        key_action={"action": "menu_clear_cache"},
    )

    assert decision.action == poll.ACTION_CLEAR_CACHE


def test_cache_terminal_from_keyboard_action() -> None:
    """Return cache_terminal when keyboard action requests cache display."""
    decision = poll.decide_poll_action(
        trigger="key_action",
        key_action={"action": "menu_cache_terminal"},
    )

    assert decision.action == poll.ACTION_CACHE_TERMINAL


def test_normal_poll_when_no_special_trigger() -> None:
    """Return normal_poll when no special trigger matches."""
    decision = poll.decide_poll_action(
        trigger="tick_model",
        key_action=None,
    )

    assert decision.action == poll.ACTION_NORMAL_POLL


def test_normal_poll_when_keyboard_action_is_irrelevant() -> None:
    """Return normal_poll when keyboard action is unrelated."""
    decision = poll.decide_poll_action(
        trigger="key_action",
        key_action={"action": "something_else"},
    )

    assert decision.action == poll.ACTION_NORMAL_POLL
