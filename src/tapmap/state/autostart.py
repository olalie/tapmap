"""Decide how the autostart control should behave."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple


class DisplayState(Enum):
    """State shown by the autostart control."""
    ON = "on"
    OFF = "off"
    UNAVAILABLE = "unavailable"


class ClickAction(Enum):
    """Action to perform when the autostart control is clicked."""
    NONE = "none"
    DISABLE = "disable"
    ENABLE = "enable"
    CREATE = "create"
    REPAIR_AND_ENABLE = "repair_and_enable"
    OPEN_SETTINGS = "open_settings"
    RECOVER_AND_ENABLE = "recover_and_enable"


class ElevationStatus(Enum):
    """Whether TapMap is running with administrator privileges."""
    NOT_ELEVATED = "not_elevated"
    ELEVATED = "elevated"
    UNKNOWN = "unknown"


class WriteOutcome(Enum):
    """Result of an autostart write attempt."""
    OK = "ok"
    CONFLICT = "conflict"
    ERROR = "error"


@dataclass(frozen=True)
class NativeAutostartStatus:
    """Current state of the operating system's autostart entry.

    Other fields are ignored when the state cannot be queried.
    """

    queryable: bool
    present: bool
    recognized: bool
    enabled: bool
    matches_preferred_definition: bool


class AutostartDecision(NamedTuple):
    """State to display and action to perform when clicked."""
    display_state: DisplayState
    click_action: ClickAction


def decide_autostart_display(
    *,
    status: NativeAutostartStatus,
    elevation: ElevationStatus,
    is_source_run: bool,
) -> AutostartDecision:
    """Return the autostart display state and click action."""
    if is_source_run:
        return AutostartDecision(DisplayState.OFF, ClickAction.NONE)

    if elevation == ElevationStatus.UNKNOWN:
        return AutostartDecision(DisplayState.UNAVAILABLE, ClickAction.NONE)

    if not status.queryable:
        return AutostartDecision(DisplayState.UNAVAILABLE, ClickAction.NONE)

    is_on = (
        status.present
        and status.recognized
        and status.enabled
        and status.matches_preferred_definition
    )

    if elevation == ElevationStatus.ELEVATED:
        # Administrator mode may read autostart state but must not change it.
        return AutostartDecision(
            DisplayState.ON if is_on else DisplayState.OFF, ClickAction.NONE
        )

    if is_on:
        return AutostartDecision(DisplayState.ON, ClickAction.DISABLE)

    if not status.present:
        return AutostartDecision(DisplayState.OFF, ClickAction.CREATE)

    if not status.recognized:
        return AutostartDecision(DisplayState.OFF, ClickAction.NONE)

    if status.matches_preferred_definition:
        return AutostartDecision(DisplayState.OFF, ClickAction.ENABLE)

    return AutostartDecision(DisplayState.OFF, ClickAction.REPAIR_AND_ENABLE)


class MacosMainAppStatus(Enum):
    """SMAppService.mainApp.status, decoupled from the framework."""
    NOT_REGISTERED = "not_registered"
    ENABLED = "enabled"
    REQUIRES_APPROVAL = "requires_approval"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class NativeMainAppStatus:
    """Current SMAppService.mainApp registration status.

    status is ignored when the state cannot be queried.
    """

    queryable: bool
    status: MacosMainAppStatus | None


def decide_macos_autostart_display(
    *,
    status: NativeMainAppStatus,
    is_source_run: bool,
) -> AutostartDecision:
    """Return the macOS autostart display state and click action."""
    if is_source_run:
        return AutostartDecision(DisplayState.OFF, ClickAction.NONE)

    if not status.queryable:
        return AutostartDecision(DisplayState.UNAVAILABLE, ClickAction.NONE)

    if status.status == MacosMainAppStatus.ENABLED:
        return AutostartDecision(DisplayState.ON, ClickAction.DISABLE)

    if status.status == MacosMainAppStatus.NOT_REGISTERED:
        return AutostartDecision(DisplayState.OFF, ClickAction.CREATE)

    if status.status == MacosMainAppStatus.REQUIRES_APPROVAL:
        return AutostartDecision(DisplayState.OFF, ClickAction.OPEN_SETTINGS)

    if status.status == MacosMainAppStatus.NOT_FOUND:
        # An error/recovery state, not OFF: shown as unavailable, but still
        # clickable, since a defined one-shot recovery exists for it.
        return AutostartDecision(DisplayState.UNAVAILABLE, ClickAction.RECOVER_AND_ENABLE)

    # Unrecognized status value: genuinely unknown, and disabled.
    return AutostartDecision(DisplayState.UNAVAILABLE, ClickAction.NONE)
