"""Tests for poll decision logic."""
import tapmap.state.poll as poll


def test_clear_cache_from_menu() -> None:
    """Return clear_cache when clear cache menu item is clicked."""
    decision = poll.decide_poll_action(
        trigger="menu_clear_cache",
        key_action=None,
    )

    assert decision.action == poll.ACTION_CLEAR_CACHE


def test_clear_cache_from_keyboard_action() -> None:
    """Return clear_cache when keyboard action requests cache clear."""
    decision = poll.decide_poll_action(
        trigger="key_action",
        key_action={"action": "menu_clear_cache"},
    )

    assert decision.action == poll.ACTION_CLEAR_CACHE


def test_normal_poll_on_tick_model_trigger() -> None:
    """Return normal_poll only when the model timer ticks."""
    decision = poll.decide_poll_action(
        trigger="tick_model",
        key_action=None,
    )

    assert decision.action == poll.ACTION_NORMAL_POLL


def test_zoom_connections_from_keyboard_action() -> None:
    """Return zoom_connections when the zoom keyboard action fires."""
    decision = poll.decide_poll_action(
        trigger="key_action",
        key_action={"action": "zoom_connections"},
    )

    assert decision.action == poll.ACTION_ZOOM_CONNECTIONS


def test_rebuild_view_from_keyboard_action() -> None:
    """Return rebuild_view when the technical-details keyboard action fires."""
    decision = poll.decide_poll_action(
        trigger="key_action",
        key_action={"action": "menu_technical_details"},
    )

    assert decision.action == poll.ACTION_REBUILD_VIEW


def test_none_when_export_cache_menu_is_clicked() -> None:
    """Return none for a trigger unrelated to the runtime model."""
    decision = poll.decide_poll_action(
        trigger="menu_export_cache",
        key_action=None,
    )

    assert decision.action == poll.ACTION_NONE


def test_none_when_geodb_management_keyboard_action_fires() -> None:
    """Return none when a keyboard action opens GeoDB management."""
    decision = poll.decide_poll_action(
        trigger="key_action",
        key_action={"action": "menu_geodb_management"},
    )

    assert decision.action == poll.ACTION_NONE


def test_none_when_export_cache_keyboard_action_fires() -> None:
    """Return none when a keyboard action requests cache export."""
    decision = poll.decide_poll_action(
        trigger="key_action",
        key_action={"action": "menu_export_cache"},
    )

    assert decision.action == poll.ACTION_NONE


def test_none_when_keyboard_action_is_irrelevant() -> None:
    """Return none when the keyboard action doesn't match any known action."""
    decision = poll.decide_poll_action(
        trigger="key_action",
        key_action={"action": "something_else"},
    )

    assert decision.action == poll.ACTION_NONE
