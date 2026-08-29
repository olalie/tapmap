"""Test Windows Task Scheduler identity rules."""

from __future__ import annotations

import pytest

from tapmap.autostart.windows_identity import (
    LOGON_TYPE_INTERACTIVE_TOKEN,
    RUN_LEVEL_LUA,
    TaskInfo,
    is_recognized_as_ours,
    matches_preferred_definition,
    normalize_path,
    normalize_user_id,
)

_EXE = r"C:\Program Files\TapMap\tapmap.exe"
_USER = "alice"


def _canonical_task(**overrides: object) -> TaskInfo:
    """Return a recognized TapMap task for the test user."""
    fields: dict[str, object] = {
        "enabled": True,
        "logon_type": LOGON_TYPE_INTERACTIVE_TOKEN,
        "run_level": RUN_LEVEL_LUA,
        "trigger_count": 1,
        "trigger_is_logon": True,
        "trigger_user_id": "alice",
        "principal_user_id": "alice",
        "action_count": 1,
        "action_path": _EXE,
        "action_arguments": "--no-browser",
    }
    fields.update(overrides)
    return TaskInfo(**fields)  # type: ignore[arg-type]


# --- normalize_user_id / normalize_path ---


def test_normalize_user_id_strips_domain_and_lowercases() -> None:
    r"""Normalize DOMAIN\user and user to the same lowercase value."""
    assert normalize_user_id("CORP\\Alice") == "alice"
    assert normalize_user_id("Alice") == "alice"


def test_normalize_path_lowercases_and_strips_quotes() -> None:
    """Normalize path case and surrounding quotes."""
    assert normalize_path(f'"{_EXE}"') == normalize_path(_EXE.lower())


# --- is_recognized_as_ours ---


def test_recognized_when_every_stable_field_matches() -> None:
    """Recognize a task when all identity fields match."""
    task = _canonical_task()

    assert is_recognized_as_ours(task, current_username=_USER, exe_path=_EXE) is True


def test_recognized_normalizes_domain_qualified_trigger_user_id() -> None:
    """Recognize a domain-qualified trigger user ID."""
    task = _canonical_task(trigger_user_id="CORP\\alice", principal_user_id="CORP\\alice")

    assert is_recognized_as_ours(task, current_username=_USER, exe_path=_EXE) is True


def test_recognized_when_legacy_task_has_no_trigger_user_id() -> None:
    """Recognize the legacy TapMap installer task."""
    task = _canonical_task(trigger_user_id=None, action_arguments=None)

    assert is_recognized_as_ours(task, current_username=_USER, exe_path=_EXE) is True


def test_not_recognized_when_trigger_is_not_logon_type_even_without_user_id() -> None:
    """Reject a non-logon trigger without a user ID."""
    task = _canonical_task(trigger_is_logon=False, trigger_user_id=None)

    assert is_recognized_as_ours(task, current_username=_USER, exe_path=_EXE) is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"logon_type": 2},  # TASK_LOGON_PASSWORD, not INTERACTIVE_TOKEN
        {"run_level": 1},  # TASK_RUNLEVEL_HIGHEST, not LUA
        {"trigger_count": 2},
        {"trigger_user_id": "bob"},  # principal still alice
        {"principal_user_id": "bob"},  # trigger still alice
        {"action_count": 2},
        {"action_path": r"C:\Other\other.exe"},
    ],
)
def test_not_recognized_when_a_stable_field_differs(overrides: dict[str, object]) -> None:
    """Reject a task when an identity field differs."""
    task = _canonical_task(**overrides)

    assert is_recognized_as_ours(task, current_username=_USER, exe_path=_EXE) is False


def test_recognized_is_independent_of_arguments() -> None:
    """Recognize ownership independently of task arguments."""
    task = _canonical_task(action_arguments="--stale-flag")

    assert is_recognized_as_ours(task, current_username=_USER, exe_path=_EXE) is True


# --- matches_preferred_definition ---


def test_matches_preferred_definition_for_exact_arguments() -> None:
    """Match the preferred --no-browser arguments."""
    task = _canonical_task(action_arguments="--no-browser")

    assert matches_preferred_definition(task) is True


def test_matches_preferred_definition_ignores_surrounding_whitespace() -> None:
    """Ignore surrounding whitespace in task arguments."""
    task = _canonical_task(action_arguments="  --no-browser  ")

    assert matches_preferred_definition(task) is True


def test_matches_preferred_definition_false_for_stale_arguments() -> None:
    """Reject outdated task arguments."""
    task = _canonical_task(action_arguments="")

    assert matches_preferred_definition(task) is False


def test_matches_preferred_definition_false_when_arguments_are_none() -> None:
    """Reject a task definition with missing arguments."""
    task = _canonical_task(action_arguments=None)

    assert matches_preferred_definition(task) is False
