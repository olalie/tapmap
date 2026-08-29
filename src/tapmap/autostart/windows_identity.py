"""Pure Task Scheduler identity rules: task name alone is not ownership."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

PREFERRED_ARGUMENTS: Final[str] = "--no-browser"

LOGON_TYPE_INTERACTIVE_TOKEN: Final[int] = 3  # TASK_LOGON_INTERACTIVE_TOKEN
RUN_LEVEL_LUA: Final[int] = 0  # TASK_RUNLEVEL_LUA
TRIGGER_TYPE_LOGON: Final[int] = 9  # TASK_TRIGGER_LOGON
ACTION_TYPE_EXEC: Final[int] = 0  # TASK_ACTION_EXEC


@dataclass(frozen=True)
class TaskInfo:
    """Raw fields read from a Task Scheduler task.

    action_path/action_arguments are None if the action isn't an Exec
    action. trigger_user_id is None if the trigger isn't a Logon trigger, or
    if it is one with no UserId set (as with the old installer's task).
    """

    enabled: bool
    logon_type: int
    run_level: int
    trigger_count: int
    trigger_is_logon: bool
    trigger_user_id: str | None
    principal_user_id: str | None
    action_count: int
    action_path: str | None
    action_arguments: str | None


def normalize_user_id(raw: str | None) -> str:
    r"""Strip a leading DOMAIN\ prefix and lowercase, for comparing UserId values."""
    if not raw:
        return ""
    _, _, name = raw.rpartition("\\")
    return name.strip().lower()


def normalize_path(raw: str | None) -> str:
    """Normalize a path string for case-insensitive comparison."""
    if not raw:
        return ""
    return raw.strip().strip('"').lower()


def is_recognized_as_ours(task: TaskInfo, *, current_username: str, exe_path: str) -> bool:
    """Return True when task's identity fields match TapMap's ownership rules.

    Ownership does not depend on the arguments matching the preferred definition.
    """
    if task.logon_type != LOGON_TYPE_INTERACTIVE_TOKEN:
        return False
    if task.run_level != RUN_LEVEL_LUA:
        return False
    if task.trigger_count != 1 or not task.trigger_is_logon:
        return False
    # The old installer's task has no Trigger.UserId. Treat that as missing
    # information, not a mismatch. A UserId that IS set must match.
    if (
        task.trigger_user_id is not None
        and normalize_user_id(task.trigger_user_id) != normalize_user_id(current_username)
    ):
        return False
    if normalize_user_id(task.principal_user_id) != normalize_user_id(current_username):
        return False
    if task.action_count != 1 or task.action_path is None:
        return False
    return normalize_path(task.action_path) == normalize_path(exe_path)


def matches_preferred_definition(task: TaskInfo) -> bool:
    """Return True when a recognized task's arguments equal the current preferred definition."""
    args = (task.action_arguments or "").strip()
    return args == PREFERRED_ARGUMENTS
