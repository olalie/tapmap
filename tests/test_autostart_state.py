"""Test autostart display and click decisions."""

from __future__ import annotations

from tapmap.state.autostart import (
    AutostartDecision,
    ClickAction,
    DisplayState,
    ElevationStatus,
    MacosMainAppStatus,
    NativeAutostartStatus,
    NativeMainAppStatus,
    decide_autostart_display,
    decide_macos_autostart_display,
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
    """Show autostart as off and disabled for a source run."""
    status = _status(
        present=True, recognized=True, enabled=True, matches_preferred_definition=True
    )

    result = decide_autostart_display(status=status, elevation=_NOT_ELEVATED, is_source_run=True)

    assert result == AutostartDecision(DisplayState.OFF, ClickAction.NONE)


def test_unqueryable_native_state_is_unavailable() -> None:
    """Show autostart as unavailable when native state cannot be read."""
    status = _status(queryable=False)

    result = decide_autostart_display(status=status, elevation=_NOT_ELEVATED, is_source_run=False)

    assert result == AutostartDecision(DisplayState.UNAVAILABLE, ClickAction.NONE)


def test_recognized_current_enabled_is_on_with_disable_action() -> None:
    """Show an enabled current TapMap task as on."""
    status = _status(
        present=True, recognized=True, enabled=True, matches_preferred_definition=True
    )

    result = decide_autostart_display(status=status, elevation=_NOT_ELEVATED, is_source_run=False)

    assert result == AutostartDecision(DisplayState.ON, ClickAction.DISABLE)


def test_absent_task_is_off_with_create_action() -> None:
    """Show autostart as off when no task exists."""
    status = _status(present=False)

    result = decide_autostart_display(status=status, elevation=_NOT_ELEVATED, is_source_run=False)

    assert result == AutostartDecision(DisplayState.OFF, ClickAction.CREATE)


def test_foreign_task_is_off_and_disabled() -> None:
    """Show autostart as off and disabled for a foreign task."""
    status = _status(present=True, recognized=False, enabled=True)

    result = decide_autostart_display(status=status, elevation=_NOT_ELEVATED, is_source_run=False)

    assert result == AutostartDecision(DisplayState.OFF, ClickAction.NONE)


def test_recognized_disabled_current_definition_is_off_with_enable_action() -> None:
    """Allow a current disabled TapMap task to be enabled."""
    status = _status(
        present=True, recognized=True, enabled=False, matches_preferred_definition=True
    )

    result = decide_autostart_display(status=status, elevation=_NOT_ELEVATED, is_source_run=False)

    assert result == AutostartDecision(DisplayState.OFF, ClickAction.ENABLE)


def test_stale_definition_is_off_with_repair_action() -> None:
    """Require repair when the TapMap task definition is outdated."""
    status = _status(
        present=True, recognized=True, enabled=True, matches_preferred_definition=False
    )

    result = decide_autostart_display(status=status, elevation=_NOT_ELEVATED, is_source_run=False)

    assert result == AutostartDecision(DisplayState.OFF, ClickAction.REPAIR_AND_ENABLE)


def test_elevated_recognized_current_enabled_shows_on_but_blocks_writes() -> None:
    """Show the current state but block changes when elevated."""
    status = _status(
        present=True, recognized=True, enabled=True, matches_preferred_definition=True
    )

    result = decide_autostart_display(status=status, elevation=_ELEVATED, is_source_run=False)

    assert result == AutostartDecision(DisplayState.ON, ClickAction.NONE)


def test_elevated_off_state_also_blocks_writes() -> None:
    """Show autostart as off and disabled when elevated."""
    status = _status(present=False)

    result = decide_autostart_display(status=status, elevation=_ELEVATED, is_source_run=False)

    assert result == AutostartDecision(DisplayState.OFF, ClickAction.NONE)


def test_unknown_elevation_is_unavailable_even_when_native_state_is_on() -> None:
    """Show autostart as unavailable when elevation cannot be determined."""
    status = _status(
        present=True, recognized=True, enabled=True, matches_preferred_definition=True
    )

    result = decide_autostart_display(
        status=status, elevation=_UNKNOWN_ELEVATION, is_source_run=False
    )

    assert result == AutostartDecision(DisplayState.UNAVAILABLE, ClickAction.NONE)


# --- decide_macos_autostart_display() ---


def _macos_status(
    *,
    queryable: bool = True,
    status: MacosMainAppStatus | None = None,
) -> NativeMainAppStatus:
    """Return a NativeMainAppStatus with the given fields."""
    return NativeMainAppStatus(queryable=queryable, status=status)


def test_macos_source_run_is_off_and_inert_regardless_of_status() -> None:
    """Show autostart as off and disabled for a source run."""
    status = _macos_status(status=MacosMainAppStatus.ENABLED)

    result = decide_macos_autostart_display(status=status, is_source_run=True)

    assert result == AutostartDecision(DisplayState.OFF, ClickAction.NONE)


def test_macos_unqueryable_status_is_unavailable() -> None:
    """Show autostart as unavailable when native status could not be read."""
    status = _macos_status(queryable=False)

    result = decide_macos_autostart_display(status=status, is_source_run=False)

    assert result == AutostartDecision(DisplayState.UNAVAILABLE, ClickAction.NONE)


def test_macos_enabled_is_on_with_disable_action() -> None:
    """Show an enabled registration as on with a disable action."""
    status = _macos_status(status=MacosMainAppStatus.ENABLED)

    result = decide_macos_autostart_display(status=status, is_source_run=False)

    assert result == AutostartDecision(DisplayState.ON, ClickAction.DISABLE)


def test_macos_not_registered_is_off_with_create_action() -> None:
    """Show autostart as off with a create action when not registered."""
    status = _macos_status(status=MacosMainAppStatus.NOT_REGISTERED)

    result = decide_macos_autostart_display(status=status, is_source_run=False)

    assert result == AutostartDecision(DisplayState.OFF, ClickAction.CREATE)


def test_macos_not_found_is_unavailable_but_recoverable() -> None:
    """Show notFound as unavailable but still recoverable."""
    status = _macos_status(status=MacosMainAppStatus.NOT_FOUND)

    result = decide_macos_autostart_display(status=status, is_source_run=False)

    assert result == AutostartDecision(DisplayState.UNAVAILABLE, ClickAction.RECOVER_AND_ENABLE)


def test_macos_requires_approval_is_off_with_open_settings_action() -> None:
    """Show requiresApproval as off, with a click that opens Login Items."""
    status = _macos_status(status=MacosMainAppStatus.REQUIRES_APPROVAL)

    result = decide_macos_autostart_display(status=status, is_source_run=False)

    assert result == AutostartDecision(DisplayState.OFF, ClickAction.OPEN_SETTINGS)
