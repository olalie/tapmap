"""Test the pure Task Scheduler ownership and preferred-definition rules."""

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
    """Return a TaskInfo that passes every recognition check for user "alice" and _EXE."""
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
    r"""A DOMAIN\user value and a bare username both normalize to the same lowercased form."""
    assert normalize_user_id("CORP\\Alice") == "alice"
    assert normalize_user_id("Alice") == "alice"


def test_normalize_path_lowercases_and_strips_quotes() -> None:
    """Quoted/differently-cased paths normalize to the same comparable form."""
    assert normalize_path(f'"{_EXE}"') == normalize_path(_EXE.lower())


# --- is_recognized_as_ours ---


def test_recognized_when_every_stable_field_matches() -> None:
    """A task matching every stable identity field is recognized as ours."""
    task = _canonical_task()

    assert is_recognized_as_ours(task, current_username=_USER, exe_path=_EXE) is True


def test_recognized_normalizes_domain_qualified_trigger_user_id() -> None:
    """A domain-qualified trigger UserId still matches the bare current username."""
    task = _canonical_task(trigger_user_id="CORP\\alice", principal_user_id="CORP\\alice")

    assert is_recognized_as_ours(task, current_username=_USER, exe_path=_EXE) is True


def test_recognized_when_legacy_task_has_no_trigger_user_id() -> None:
    """The old installer's task shape is recognized as ours."""
    task = _canonical_task(trigger_user_id=None, action_arguments=None)

    assert is_recognized_as_ours(task, current_username=_USER, exe_path=_EXE) is True


def test_not_recognized_when_trigger_is_not_logon_type_even_without_user_id() -> None:
    """A non-Logon trigger with no UserId is still rejected, not mistaken for a legacy task."""
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
    """Any mismatched identity field means the task is never recognized as ours."""
    task = _canonical_task(**overrides)

    assert is_recognized_as_ours(task, current_username=_USER, exe_path=_EXE) is False


def test_recognized_is_independent_of_arguments() -> None:
    """Ownership doesn't depend on the arguments matching the preferred definition."""
    task = _canonical_task(action_arguments="--stale-flag")

    assert is_recognized_as_ours(task, current_username=_USER, exe_path=_EXE) is True


# --- matches_preferred_definition ---


def test_matches_preferred_definition_for_exact_arguments() -> None:
    """Arguments equal to --no-browser match the preferred definition."""
    task = _canonical_task(action_arguments="--no-browser")

    assert matches_preferred_definition(task) is True


def test_matches_preferred_definition_ignores_surrounding_whitespace() -> None:
    """Harmless surrounding whitespace in the stored arguments is normalized away."""
    task = _canonical_task(action_arguments="  --no-browser  ")

    assert matches_preferred_definition(task) is True


def test_matches_preferred_definition_false_for_stale_arguments() -> None:
    """Arguments that don't equal --no-browser are stale, even if the task is otherwise ours."""
    task = _canonical_task(action_arguments="")

    assert matches_preferred_definition(task) is False


def test_matches_preferred_definition_false_when_arguments_are_none() -> None:
    """A missing Arguments value is treated as not matching, not as an error."""
    task = _canonical_task(action_arguments=None)

    assert matches_preferred_definition(task) is False
