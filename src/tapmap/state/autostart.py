"""Pure decision logic for the "Run TapMap automatically" control.

Native OS state is the source of truth; nothing here is cached.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple


class DisplayState(Enum):
    """What the "Run TapMap automatically" control should show."""

    ON = "on"
    OFF = "off"
    UNAVAILABLE = "unavailable"


class ClickAction(Enum):
    """What a click on the control should do, given its current decision."""

    NONE = "none"
    DISABLE = "disable"
    ENABLE = "enable"
    CREATE = "create"
    REPAIR_AND_ENABLE = "repair_and_enable"
    SHOW_CONFLICT = "show_conflict"


class ElevationStatus(Enum):
    """Whether the current process is running elevated.

    UNKNOWN is never treated as NOT_ELEVATED.
    """

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
    """Snapshot of the native autostart mechanism.

    Other fields are meaningless when queryable is False.
    """

    queryable: bool
    present: bool
    recognized: bool
    enabled: bool
    matches_preferred_definition: bool


class AutostartDecision(NamedTuple):
    """Display state and click action for the autostart control."""

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
        # Elevated may read and display live state, but never write.
        return AutostartDecision(
            DisplayState.ON if is_on else DisplayState.OFF, ClickAction.NONE
        )

    if is_on:
        return AutostartDecision(DisplayState.ON, ClickAction.DISABLE)

    if not status.present:
        return AutostartDecision(DisplayState.OFF, ClickAction.CREATE)

    if not status.recognized:
        return AutostartDecision(DisplayState.OFF, ClickAction.SHOW_CONFLICT)

    if status.matches_preferred_definition:
        return AutostartDecision(DisplayState.OFF, ClickAction.ENABLE)

    return AutostartDecision(DisplayState.OFF, ClickAction.REPAIR_AND_ENABLE)
