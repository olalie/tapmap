"""Windows autostart orchestration: Task Scheduler backend, identity rules, and the setup marker."""

from __future__ import annotations

import ctypes
import getpass
import logging
from pathlib import Path

from tapmap.state.autostart import (
    AutostartDecision,
    ElevationStatus,
    NativeAutostartStatus,
    WriteOutcome,
    decide_autostart_display,
)

from . import marker
from . import windows_task_scheduler as scheduler
from .windows_identity import (
    PREFERRED_ARGUMENTS,
    TaskInfo,
    is_recognized_as_ours,
    matches_preferred_definition,
)

logger = logging.getLogger(__name__)

_UNREADABLE_STATUS = NativeAutostartStatus(
    queryable=False,
    present=False,
    recognized=False,
    enabled=False,
    matches_preferred_definition=False,
)


def is_elevated() -> ElevationStatus:
    """Return whether the current process is running elevated.

    Returns UNKNOWN, never NOT_ELEVATED, if the check fails.
    """
    try:
        return (
            ElevationStatus.ELEVATED
            if ctypes.windll.shell32.IsUserAnAdmin()
            else ElevationStatus.NOT_ELEVATED
        )
    except (OSError, AttributeError):
        return ElevationStatus.UNKNOWN


def _current_username() -> str:
    """Return the current OS username."""
    return getpass.getuser()


def _classify(task: TaskInfo | None, *, exe_path: str) -> NativeAutostartStatus:
    """Classify a task into a NativeAutostartStatus."""
    if task is None:
        return NativeAutostartStatus(
            queryable=True,
            present=False,
            recognized=False,
            enabled=False,
            matches_preferred_definition=False,
        )

    recognized = is_recognized_as_ours(
        task, current_username=_current_username(), exe_path=exe_path
    )
    if not recognized:
        return NativeAutostartStatus(
            queryable=True,
            present=True,
            recognized=False,
            enabled=task.enabled,
            matches_preferred_definition=False,
        )

    return NativeAutostartStatus(
        queryable=True,
        present=True,
        recognized=True,
        enabled=task.enabled,
        matches_preferred_definition=matches_preferred_definition(task),
    )


def query_display_state(*, exe_path: str, is_frozen: bool) -> AutostartDecision:
    """Return the current display state and click action for the R control.

    A source run (is_frozen False) never queries Task Scheduler at all.
    """
    if not is_frozen:
        return decide_autostart_display(
            status=_UNREADABLE_STATUS,
            elevation=ElevationStatus.NOT_ELEVATED,
            is_source_run=True,
        )

    try:
        task = scheduler.find_task()
        status = _classify(task, exe_path=exe_path)
    except scheduler.TaskQueryError:
        status = _UNREADABLE_STATUS

    return decide_autostart_display(status=status, elevation=is_elevated(), is_source_run=False)


def enable(*, exe_path: str) -> tuple[WriteOutcome, str | None]:
    """Enable the existing task, re-verifying ownership before the write.

    error_message is only set for ERROR.
    """
    try:
        scheduler.set_task_enabled_if_recognized(
            True, current_username=_current_username(), exe_path=exe_path
        )
        return WriteOutcome.OK, None
    except scheduler.TaskOwnershipConflict:
        return WriteOutcome.CONFLICT, None
    except scheduler.TaskQueryError as exc:
        return WriteOutcome.ERROR, str(exc)


def disable(*, exe_path: str) -> tuple[WriteOutcome, str | None]:
    """Disable the existing task, re-verifying ownership before the write."""
    try:
        scheduler.set_task_enabled_if_recognized(
            False, current_username=_current_username(), exe_path=exe_path
        )
        return WriteOutcome.OK, None
    except scheduler.TaskOwnershipConflict:
        return WriteOutcome.CONFLICT, None
    except scheduler.TaskQueryError as exc:
        return WriteOutcome.ERROR, str(exc)


def create(*, exe_path: str) -> tuple[WriteOutcome, str | None]:
    """Create the canonical enabled task, refusing if a non-recognized task now exists."""
    try:
        scheduler.create_or_update_task_if_owned_or_absent(
            exe_path=exe_path,
            arguments=PREFERRED_ARGUMENTS,
            username=_current_username(),
        )
        return WriteOutcome.OK, None
    except scheduler.TaskOwnershipConflict:
        return WriteOutcome.CONFLICT, None
    except scheduler.TaskQueryError as exc:
        return WriteOutcome.ERROR, str(exc)


def repair_and_enable(*, exe_path: str) -> tuple[WriteOutcome, str | None]:
    """Update a recognized-but-stale task in place, refusing if it's no longer recognized."""
    return create(exe_path=exe_path)


def run_startup_setup(*, app_data_dir: Path, exe_path: str, is_frozen: bool) -> None:
    """Run the marker-absent startup state machine, if applicable.

    Never raises: startup must continue regardless of outcome.
    """
    if not is_frozen:
        return
    if marker.has_completed_setup(app_data_dir):
        return

    try:
        task = scheduler.find_task()
    except scheduler.TaskQueryError:
        logger.warning("Unable to query Task Scheduler for initial autostart setup.")
        return

    if task is not None:
        # Task already exists; don't touch it.
        marker.mark_setup_completed(app_data_dir)
        return

    if is_elevated() != ElevationStatus.NOT_ELEVATED:
        # Blocks both elevated and unknown status.
        return

    try:
        scheduler.create_or_update_task_if_owned_or_absent(
            exe_path=exe_path,
            arguments=PREFERRED_ARGUMENTS,
            username=_current_username(),
        )
    except scheduler.TaskOwnershipConflict:
        # A task appeared since the check above; treat as already present.
        marker.mark_setup_completed(app_data_dir)
        return
    except scheduler.TaskQueryError:
        logger.warning("Unable to create the initial TapMap autostart task.")
        return

    if not _verify_created_task(exe_path=exe_path):
        logger.warning(
            "Unable to verify the newly created TapMap autostart task; leaving "
            "initial setup incomplete so a later launch retries."
        )
        return

    marker.mark_setup_completed(app_data_dir)


def _verify_created_task(*, exe_path: str) -> bool:
    """Read back the just-created task and confirm it matches the canonical definition."""
    try:
        task = scheduler.find_task()
    except scheduler.TaskQueryError:
        return False

    if task is None:
        return False

    if not is_recognized_as_ours(task, current_username=_current_username(), exe_path=exe_path):
        return False

    if not task.enabled:
        return False

    return matches_preferred_definition(task)
