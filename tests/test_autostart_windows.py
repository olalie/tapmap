"""Test Windows autostart orchestration: startup state machine and live query/write actions.

Task Scheduler I/O is mocked at the windows_task_scheduler module boundary
(mirrors how test_appinfo_windows.py mocks windows_signature_info) so these
tests never touch the real Task Scheduler.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapmap.autostart import marker, windows_autostart
from tapmap.autostart import windows_task_scheduler as scheduler
from tapmap.autostart.windows_identity import TaskInfo
from tapmap.state.autostart import ClickAction, DisplayState, ElevationStatus, WriteOutcome

_EXE = r"C:\Program Files\TapMap\tapmap.exe"
_CURRENT_USER = object()  # sentinel: "use the current username"


def _recognized_task(
    *,
    enabled: bool = True,
    arguments: str | None = "--no-browser",
    trigger_user_id: object = _CURRENT_USER,
) -> TaskInfo:
    """Return a recognized TaskInfo for the current user and _EXE."""
    if trigger_user_id is _CURRENT_USER:
        trigger_user_id = windows_autostart._current_username()
    return TaskInfo(
        enabled=enabled,
        logon_type=3,
        run_level=0,
        trigger_count=1,
        trigger_is_logon=True,
        trigger_user_id=trigger_user_id,
        principal_user_id=windows_autostart._current_username(),
        action_count=1,
        action_path=_EXE,
        action_arguments=arguments,
    )


# --- query_display_state() ---


def test_query_display_state_is_off_for_a_source_run_and_never_queries_scheduler(
    monkeypatch,
) -> None:
    """A source run never touches Task Scheduler at all."""
    called = False

    def _fail(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("Task Scheduler must not be queried for a source run")

    monkeypatch.setattr(scheduler, "find_task", _fail)

    decision = windows_autostart.query_display_state(exe_path="", is_frozen=False)

    assert decision.display_state == DisplayState.OFF
    assert decision.click_action == ClickAction.NONE
    assert called is False


def test_query_display_state_on_for_recognized_current_enabled_task(monkeypatch) -> None:
    """A frozen run with a recognized, enabled, current-definition task shows ON."""
    monkeypatch.setattr(scheduler, "find_task", lambda: _recognized_task())
    monkeypatch.setattr(windows_autostart, "is_elevated", lambda: ElevationStatus.NOT_ELEVATED)

    decision = windows_autostart.query_display_state(exe_path=_EXE, is_frozen=True)

    assert decision.display_state == DisplayState.ON
    assert decision.click_action == ClickAction.DISABLE


def test_query_display_state_off_repair_for_legacy_installer_task(monkeypatch) -> None:
    """The old installer's task (no Trigger.UserId, no Arguments) needs repair."""
    legacy_task = _recognized_task(arguments=None, trigger_user_id=None)
    monkeypatch.setattr(scheduler, "find_task", lambda: legacy_task)
    monkeypatch.setattr(windows_autostart, "is_elevated", lambda: ElevationStatus.NOT_ELEVATED)

    decision = windows_autostart.query_display_state(exe_path=_EXE, is_frozen=True)

    assert decision.display_state == DisplayState.OFF
    assert decision.click_action == ClickAction.REPAIR_AND_ENABLE


def test_query_display_state_off_for_absent_task(monkeypatch) -> None:
    """No task at all shows OFF with a create action."""
    monkeypatch.setattr(scheduler, "find_task", lambda: None)
    monkeypatch.setattr(windows_autostart, "is_elevated", lambda: ElevationStatus.NOT_ELEVATED)

    decision = windows_autostart.query_display_state(exe_path=_EXE, is_frozen=True)

    assert decision.display_state == DisplayState.OFF
    assert decision.click_action == ClickAction.CREATE


def test_query_display_state_unavailable_when_scheduler_raises(monkeypatch) -> None:
    """A query failure degrades to Unavailable, never an exception."""

    def _raise():
        raise scheduler.TaskQueryError("boom")

    monkeypatch.setattr(scheduler, "find_task", _raise)

    decision = windows_autostart.query_display_state(exe_path=_EXE, is_frozen=True)

    assert decision.display_state == DisplayState.UNAVAILABLE
    assert decision.click_action == ClickAction.NONE


def test_query_display_state_unavailable_when_elevation_cannot_be_determined(
    monkeypatch,
) -> None:
    """An undetermined elevation status is Unavailable, never treated as non-elevated."""
    monkeypatch.setattr(scheduler, "find_task", lambda: _recognized_task())
    monkeypatch.setattr(windows_autostart, "is_elevated", lambda: ElevationStatus.UNKNOWN)

    decision = windows_autostart.query_display_state(exe_path=_EXE, is_frozen=True)

    assert decision.display_state == DisplayState.UNAVAILABLE
    assert decision.click_action == ClickAction.NONE


# --- write actions ---
#
# All writes go through the single-session guarded backend functions.


def test_enable_reports_scheduler_failure(monkeypatch) -> None:
    """A failed write is reported as (ERROR, message), never raised."""

    def _raise(_enabled, **_kwargs):
        raise scheduler.TaskQueryError("access denied")

    monkeypatch.setattr(scheduler, "set_task_enabled_if_recognized", _raise)

    outcome, error = windows_autostart.enable(exe_path=_EXE)

    assert outcome == WriteOutcome.ERROR
    assert error == "access denied"


def test_disable_calls_set_task_enabled_if_recognized_false(monkeypatch) -> None:
    """disable() flips the existing task off in place."""
    calls: list[tuple[bool, str, str]] = []
    monkeypatch.setattr(
        scheduler,
        "set_task_enabled_if_recognized",
        lambda enabled, *, current_username, exe_path: calls.append(
            (enabled, current_username, exe_path)
        ),
    )

    outcome, error = windows_autostart.disable(exe_path=_EXE)

    assert outcome == WriteOutcome.OK
    assert error is None
    assert calls == [(False, windows_autostart._current_username(), _EXE)]


def test_disable_reports_ownership_conflict_without_writing(monkeypatch) -> None:
    """disable() surfaces a write-time conflict distinctly, without performing any write."""

    def _raise(_enabled, **_kwargs):
        raise scheduler.TaskOwnershipConflict("not ours anymore")

    monkeypatch.setattr(scheduler, "set_task_enabled_if_recognized", _raise)

    outcome, error = windows_autostart.disable(exe_path=_EXE)

    assert outcome == WriteOutcome.CONFLICT
    assert error is None


def test_create_passes_preferred_arguments_and_current_username(monkeypatch) -> None:
    """create() always uses the canonical --no-browser arguments."""
    captured: dict[str, object] = {}

    def _create_or_update(*, exe_path, arguments, username):
        captured.update(exe_path=exe_path, arguments=arguments, username=username)

    monkeypatch.setattr(scheduler, "create_or_update_task_if_owned_or_absent", _create_or_update)

    outcome, error = windows_autostart.create(exe_path=_EXE)

    assert outcome == WriteOutcome.OK
    assert error is None
    assert captured["exe_path"] == _EXE
    assert captured["arguments"] == "--no-browser"


def test_create_reports_ownership_conflict_without_writing(monkeypatch) -> None:
    """create() surfaces a write-time conflict distinctly (a foreign task appeared)."""

    def _raise(**_kwargs):
        raise scheduler.TaskOwnershipConflict("a task now exists and is not ours")

    monkeypatch.setattr(scheduler, "create_or_update_task_if_owned_or_absent", _raise)

    outcome, error = windows_autostart.create(exe_path=_EXE)

    assert outcome == WriteOutcome.CONFLICT
    assert error is None


# --- run_startup_setup(): the marker-absent state machine ---


def test_startup_setup_noop_for_source_run(tmp_path: Path, monkeypatch) -> None:
    """A source run never queries Task Scheduler and never writes the marker."""
    called = False

    def _fail():
        nonlocal called
        called = True
        raise AssertionError("must not query for a source run")

    monkeypatch.setattr(scheduler, "find_task", _fail)

    windows_autostart.run_startup_setup(app_data_dir=tmp_path, exe_path="", is_frozen=False)

    assert called is False
    assert marker.has_completed_setup(tmp_path) is False


def test_startup_setup_noop_once_marker_exists(tmp_path: Path, monkeypatch) -> None:
    """Once the marker exists, ordinary startup never touches Task Scheduler again."""
    marker.mark_setup_completed(tmp_path)
    called = False

    def _fail():
        nonlocal called
        called = True
        raise AssertionError("must not query once the marker exists")

    monkeypatch.setattr(scheduler, "find_task", _fail)

    windows_autostart.run_startup_setup(app_data_dir=tmp_path, exe_path=_EXE, is_frozen=True)

    assert called is False


def test_startup_setup_creates_task_and_writes_marker_when_absent(
    tmp_path: Path, monkeypatch
) -> None:
    """Marker absent + no task: create the canonical task, verify it, then write the marker."""
    find_task_calls: list[None] = []

    def _find_task():
        find_task_calls.append(None)
        # First call (pre-create query): no task yet. Second call (post-create
        # read-back verification): the task now exists as created.
        return None if len(find_task_calls) == 1 else _recognized_task()

    monkeypatch.setattr(scheduler, "find_task", _find_task)
    monkeypatch.setattr(windows_autostart, "is_elevated", lambda: ElevationStatus.NOT_ELEVATED)
    created: dict[str, object] = {}
    monkeypatch.setattr(
        scheduler,
        "create_or_update_task_if_owned_or_absent",
        lambda **kwargs: created.update(kwargs),
    )

    windows_autostart.run_startup_setup(app_data_dir=tmp_path, exe_path=_EXE, is_frozen=True)

    assert created["exe_path"] == _EXE
    assert len(find_task_calls) == 2
    assert marker.has_completed_setup(tmp_path) is True


def test_startup_setup_does_not_write_marker_when_post_create_readback_fails_verification(
    tmp_path: Path, monkeypatch
) -> None:
    """Creation succeeds but the read-back shows the task disabled: marker stays absent."""
    find_task_calls: list[None] = []

    def _find_task():
        find_task_calls.append(None)
        return None if len(find_task_calls) == 1 else _recognized_task(enabled=False)

    monkeypatch.setattr(scheduler, "find_task", _find_task)
    monkeypatch.setattr(windows_autostart, "is_elevated", lambda: ElevationStatus.NOT_ELEVATED)
    monkeypatch.setattr(
        scheduler, "create_or_update_task_if_owned_or_absent", lambda **_kwargs: None
    )

    windows_autostart.run_startup_setup(app_data_dir=tmp_path, exe_path=_EXE, is_frozen=True)

    assert marker.has_completed_setup(tmp_path) is False


def test_startup_setup_does_not_write_marker_when_post_create_readback_is_ambiguous(
    tmp_path: Path, monkeypatch
) -> None:
    """Creation succeeds but the verification read-back itself fails: marker stays absent."""
    find_task_calls: list[None] = []

    def _find_task():
        find_task_calls.append(None)
        if len(find_task_calls) == 1:
            return None
        raise scheduler.TaskQueryError("boom")

    monkeypatch.setattr(scheduler, "find_task", _find_task)
    monkeypatch.setattr(windows_autostart, "is_elevated", lambda: ElevationStatus.NOT_ELEVATED)
    monkeypatch.setattr(
        scheduler, "create_or_update_task_if_owned_or_absent", lambda **_kwargs: None
    )

    windows_autostart.run_startup_setup(app_data_dir=tmp_path, exe_path=_EXE, is_frozen=True)

    assert marker.has_completed_setup(tmp_path) is False


def test_startup_setup_writes_marker_without_touching_an_existing_task(
    tmp_path: Path, monkeypatch
) -> None:
    """Marker absent + a task already exists: write the marker, never touch the task."""
    monkeypatch.setattr(scheduler, "find_task", lambda: _recognized_task())

    def _fail(**_kwargs):
        raise AssertionError("must not create/update an already-existing task")

    monkeypatch.setattr(scheduler, "create_or_update_task_if_owned_or_absent", _fail)

    windows_autostart.run_startup_setup(app_data_dir=tmp_path, exe_path=_EXE, is_frozen=True)

    assert marker.has_completed_setup(tmp_path) is True


def test_startup_setup_writes_marker_when_write_time_ownership_conflict_occurs(
    tmp_path: Path, monkeypatch
) -> None:
    """A write-time conflict still completes initial setup, unlike an ambiguous query failure."""
    monkeypatch.setattr(scheduler, "find_task", lambda: None)
    monkeypatch.setattr(windows_autostart, "is_elevated", lambda: ElevationStatus.NOT_ELEVATED)

    def _raise(**_kwargs):
        raise scheduler.TaskOwnershipConflict("a task now exists and is not ours")

    monkeypatch.setattr(scheduler, "create_or_update_task_if_owned_or_absent", _raise)

    windows_autostart.run_startup_setup(app_data_dir=tmp_path, exe_path=_EXE, is_frozen=True)

    assert marker.has_completed_setup(tmp_path) is True


def test_startup_setup_does_nothing_when_scheduler_is_unreadable(
    tmp_path: Path, monkeypatch
) -> None:
    """A query failure performs no write and does not write the marker."""

    def _raise():
        raise scheduler.TaskQueryError("boom")

    monkeypatch.setattr(scheduler, "find_task", _raise)

    windows_autostart.run_startup_setup(app_data_dir=tmp_path, exe_path=_EXE, is_frozen=True)

    assert marker.has_completed_setup(tmp_path) is False


def test_startup_setup_does_not_create_task_or_marker_when_elevated(
    tmp_path: Path, monkeypatch
) -> None:
    """An elevated process with no task must not create one or write the marker."""
    monkeypatch.setattr(scheduler, "find_task", lambda: None)
    monkeypatch.setattr(windows_autostart, "is_elevated", lambda: ElevationStatus.ELEVATED)

    def _fail(**_kwargs):
        raise AssertionError("elevated must never create the task")

    monkeypatch.setattr(scheduler, "create_or_update_task_if_owned_or_absent", _fail)

    windows_autostart.run_startup_setup(app_data_dir=tmp_path, exe_path=_EXE, is_frozen=True)

    assert marker.has_completed_setup(tmp_path) is False


def test_startup_setup_does_not_create_task_or_marker_when_elevation_is_unknown(
    tmp_path: Path, monkeypatch
) -> None:
    """An undetermined elevation status must block creation exactly like confirmed elevation."""
    monkeypatch.setattr(scheduler, "find_task", lambda: None)
    monkeypatch.setattr(windows_autostart, "is_elevated", lambda: ElevationStatus.UNKNOWN)

    def _fail(**_kwargs):
        raise AssertionError("undetermined elevation must never create the task")

    monkeypatch.setattr(scheduler, "create_or_update_task_if_owned_or_absent", _fail)

    windows_autostart.run_startup_setup(app_data_dir=tmp_path, exe_path=_EXE, is_frozen=True)

    assert marker.has_completed_setup(tmp_path) is False


def test_startup_setup_does_not_write_marker_when_creation_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """A failed create leaves the marker absent so a later launch retries."""
    monkeypatch.setattr(scheduler, "find_task", lambda: None)
    monkeypatch.setattr(windows_autostart, "is_elevated", lambda: ElevationStatus.NOT_ELEVATED)

    def _raise(**_kwargs):
        raise scheduler.TaskQueryError("boom")

    monkeypatch.setattr(scheduler, "create_or_update_task_if_owned_or_absent", _raise)

    windows_autostart.run_startup_setup(app_data_dir=tmp_path, exe_path=_EXE, is_frozen=True)

    assert marker.has_completed_setup(tmp_path) is False


# --- is_elevated() ---


def test_is_elevated_maps_true_and_false_correctly(monkeypatch) -> None:
    """IsUserAnAdmin() True/False map to ELEVATED/NOT_ELEVATED."""
    import ctypes

    if not hasattr(ctypes, "windll"):
        pytest.skip("Windows-only: requires ctypes.windll")

    monkeypatch.setattr(ctypes.windll.shell32, "IsUserAnAdmin", lambda: True)
    assert windows_autostart.is_elevated() == ElevationStatus.ELEVATED

    monkeypatch.setattr(ctypes.windll.shell32, "IsUserAnAdmin", lambda: False)
    assert windows_autostart.is_elevated() == ElevationStatus.NOT_ELEVATED


def test_is_elevated_returns_unknown_rather_than_raising_off_windows(monkeypatch) -> None:
    """is_elevated() degrades to UNKNOWN, never NOT_ELEVATED, when the Win32 call is unavailable."""
    import ctypes

    if hasattr(ctypes, "windll"):
        pytest.skip("only meaningful where ctypes.windll doesn't exist")

    assert windows_autostart.is_elevated() == ElevationStatus.UNKNOWN
