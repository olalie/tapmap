"""Test the pure "Run TapMap automatically" display/click decision table."""

from __future__ import annotations

from tapmap.state.autostart import (
    AutostartDecision,
    ClickAction,
    DisplayState,
    ElevationStatus,
    NativeAutostartStatus,
    decide_autostart_display,
)

_NOT_ELEVATED = ElevationStatus.NOT_ELEVATED
_ELEVATED = ElevationStatus.ELEVATED
_UNKNOWN_ELEVATION = ElevationStatus.UNKNOWN


def _status(
    *,
    queryable: bool = True,
    present: bool = False,
    recognized: bool = False,
    enabled: bool = False,
    matches_preferred_definition: bool = False,
) -> NativeAutostartStatus:
    """Return a NativeAutostartStatus with the given fields."""
    return NativeAutostartStatus(
        queryable=queryable,
        present=present,
        recognized=recognized,
        enabled=enabled,
        matches_preferred_definition=matches_preferred_definition,
    )


def test_source_run_is_off_and_inert_regardless_of_status() -> None:
    """A source run never queries native state, so it always shows OFF with no click action."""
    status = _status(
        present=True, recognized=True, enabled=True, matches_preferred_definition=True
    )

    result = decide_autostart_display(status=status, elevation=_NOT_ELEVATED, is_source_run=True)

    assert result == AutostartDecision(DisplayState.OFF, ClickAction.NONE)


def test_unqueryable_native_state_is_unavailable() -> None:
    """Native state that can't be read reliably shows Unavailable and blocks writes."""
    status = _status(queryable=False)

    result = decide_autostart_display(status=status, elevation=_NOT_ELEVATED, is_source_run=False)

    assert result == AutostartDecision(DisplayState.UNAVAILABLE, ClickAction.NONE)


def test_recognized_current_enabled_is_on_with_disable_action() -> None:
    """A recognized, enabled task matching the preferred definition displays ON."""
    status = _status(
        present=True, recognized=True, enabled=True, matches_preferred_definition=True
    )

    result = decide_autostart_display(status=status, elevation=_NOT_ELEVATED, is_source_run=False)

    assert result == AutostartDecision(DisplayState.ON, ClickAction.DISABLE)


def test_absent_task_is_off_with_create_action() -> None:
    """No task at all displays OFF and a click should create the canonical task."""
    status = _status(present=False)

    result = decide_autostart_display(status=status, elevation=_NOT_ELEVATED, is_source_run=False)

    assert result == AutostartDecision(DisplayState.OFF, ClickAction.CREATE)


def test_foreign_task_is_off_with_conflict_action() -> None:
    """A present but non-recognized task never gets modified; a click surfaces the conflict."""
    status = _status(present=True, recognized=False, enabled=True)

    result = decide_autostart_display(status=status, elevation=_NOT_ELEVATED, is_source_run=False)

    assert result == AutostartDecision(DisplayState.OFF, ClickAction.SHOW_CONFLICT)


def test_recognized_disabled_current_definition_is_off_with_enable_action() -> None:
    """A recognized, disabled task already matching the preferred definition just needs enabling."""
    status = _status(
        present=True, recognized=True, enabled=False, matches_preferred_definition=True
    )

    result = decide_autostart_display(status=status, elevation=_NOT_ELEVATED, is_source_run=False)

    assert result == AutostartDecision(DisplayState.OFF, ClickAction.ENABLE)


def test_stale_definition_is_off_with_repair_action() -> None:
    """A recognized task with a stale definition needs the repair action, enabled or not."""
    status = _status(
        present=True, recognized=True, enabled=True, matches_preferred_definition=False
    )

    result = decide_autostart_display(status=status, elevation=_NOT_ELEVATED, is_source_run=False)

    assert result == AutostartDecision(DisplayState.OFF, ClickAction.REPAIR_AND_ENABLE)


def test_elevated_recognized_current_enabled_shows_on_but_blocks_writes() -> None:
    """Elevated may read and display live state, but a click never performs any write."""
    status = _status(
        present=True, recognized=True, enabled=True, matches_preferred_definition=True
    )

    result = decide_autostart_display(status=status, elevation=_ELEVATED, is_source_run=False)

    assert result == AutostartDecision(DisplayState.ON, ClickAction.NONE)


def test_elevated_off_state_also_blocks_writes() -> None:
    """Elevated with no active task displays OFF, still with no click action."""
    status = _status(present=False)

    result = decide_autostart_display(status=status, elevation=_ELEVATED, is_source_run=False)

    assert result == AutostartDecision(DisplayState.OFF, ClickAction.NONE)


def test_unknown_elevation_is_unavailable_even_when_native_state_is_on() -> None:
    """An undetermined elevation status is unavailable/read-only, never treated as non-elevated."""
    status = _status(
        present=True, recognized=True, enabled=True, matches_preferred_definition=True
    )

    result = decide_autostart_display(
        status=status, elevation=_UNKNOWN_ELEVATION, is_source_run=False
    )

    assert result == AutostartDecision(DisplayState.UNAVAILABLE, ClickAction.NONE)
