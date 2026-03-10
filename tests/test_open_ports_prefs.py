"""Tests for Open Ports preference handling."""

import state.open_ports_prefs as prefs


def test_set_show_system_pref_turns_on_flag() -> None:
    """Set show_system to True when toggle contains 'on'."""
    result = prefs.set_show_system_pref(
        toggle_value=["on"],
        prefs_data={},
    )

    assert result["show_system"] is True


def test_set_show_system_pref_turns_off_flag() -> None:
    """Set show_system to False when toggle is not active."""
    result = prefs.set_show_system_pref(
        toggle_value=[],
        prefs_data={},
    )

    assert result["show_system"] is False


def test_set_show_system_pref_handles_non_dict_prefs() -> None:
    """Create new preferences dict when prefs_data is invalid."""
    result = prefs.set_show_system_pref(
        toggle_value=["on"],
        prefs_data=None,
    )

    assert result == {"show_system": True}


def test_set_show_system_pref_preserves_existing_preferences() -> None:
    """Preserve unrelated preference fields."""
    result = prefs.set_show_system_pref(
        toggle_value=["on"],
        prefs_data={"foo": 1},
    )

    assert result["foo"] == 1
    assert result["show_system"] is True
