"""Test Linux autostart behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapmap.autostart import linux_autostart, marker
from tapmap.state.autostart import ClickAction, DisplayState, WriteOutcome

_EXE = "/usr/lib/tapmap/tapmap"


def _entry(tmp_path: Path, monkeypatch, text: str | bytes | None) -> Path:
    """Create a test autostart entry with optional content."""
    path = tmp_path / "autostart" / "no.tip.tapmap.desktop"
    monkeypatch.setattr(linux_autostart, "_entry_path", lambda: path)
    if text is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            path.write_bytes(text)
        else:
            path.write_text(text, encoding="utf-8")
    return path


_CANONICAL = (
    "[Desktop Entry]\n"
    "Type=Application\n"
    "Name=TapMap\n"
    "Exec=/usr/lib/tapmap/tapmap --no-browser\n"
    "Terminal=false\n"
)

_WITH_COMMENTS_AND_EXTRA_KEYS = (
    "# a comment above the group\n"
    "[Desktop Entry]\n"
    "Type=Application\n"
    "Name=TapMap\n"
    "# a comment inside the group\n"
    "Exec=/usr/lib/tapmap/tapmap --no-browser\n"
    "Terminal=false\n"
    "X-Some-Other-Key=keep-me\n"
)


# --- query_display_state() ---


def test_query_display_state_is_off_for_a_source_run_and_never_reads(monkeypatch) -> None:
    """Do not read the entry for a source run."""

    def _fail():
        """Fail the test if called."""
        raise AssertionError("must not read the native entry for a source run")

    monkeypatch.setattr(linux_autostart, "_query_native_status", _fail)

    decision = linux_autostart.query_display_state(is_frozen=False)

    assert decision.display_state == DisplayState.OFF
    assert decision.click_action == ClickAction.NONE


def test_query_display_state_on_for_absent_hidden_key(tmp_path: Path, monkeypatch) -> None:
    """Show on when Hidden= is absent."""
    _entry(tmp_path, monkeypatch, _CANONICAL)

    decision = linux_autostart.query_display_state(is_frozen=True)

    assert decision.display_state == DisplayState.ON
    assert decision.click_action == ClickAction.DISABLE


def test_query_display_state_on_for_hidden_false(tmp_path: Path, monkeypatch) -> None:
    """Show on when Hidden=false."""
    _entry(tmp_path, monkeypatch, _CANONICAL + "Hidden=false\n")

    decision = linux_autostart.query_display_state(is_frozen=True)

    assert decision.display_state == DisplayState.ON
    assert decision.click_action == ClickAction.DISABLE


def test_query_display_state_off_for_hidden_true(tmp_path: Path, monkeypatch) -> None:
    """Show off with an enable action when Hidden=true."""
    _entry(tmp_path, monkeypatch, _CANONICAL + "Hidden=true\n")

    decision = linux_autostart.query_display_state(is_frozen=True)

    assert decision.display_state == DisplayState.OFF
    assert decision.click_action == ClickAction.ENABLE


def test_query_display_state_off_with_create_action_when_absent(
    tmp_path: Path, monkeypatch
) -> None:
    """Show off with a create action when no entry exists."""
    _entry(tmp_path, monkeypatch, None)

    decision = linux_autostart.query_display_state(is_frozen=True)

    assert decision.display_state == DisplayState.OFF
    assert decision.click_action == ClickAction.CREATE


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("not a desktop entry at all\n", id="no_group_header"),
        pytest.param("[Desktop Entry]\nHidden=maybe\n", id="unrecognized_hidden_value"),
    ],
)
def test_query_display_state_unavailable_for_malformed_entry(
    tmp_path: Path, monkeypatch, text: str
) -> None:
    """Show a malformed entry as unavailable with no click action."""
    _entry(tmp_path, monkeypatch, text)

    decision = linux_autostart.query_display_state(is_frozen=True)

    assert decision.display_state == DisplayState.UNAVAILABLE
    assert decision.click_action == ClickAction.NONE


def test_query_display_state_unavailable_when_entry_directory_unreadable(
    tmp_path: Path, monkeypatch
) -> None:
    """Show unavailable when the entry cannot be read."""

    class _UnreadablePath(Path):
        def is_file(self):
            """Raise OSError instead of reporting whether the path is a file."""
            raise OSError("denied")

    monkeypatch.setattr(linux_autostart, "_entry_path", lambda: _UnreadablePath(tmp_path / "x"))

    decision = linux_autostart.query_display_state(is_frozen=True)

    assert decision.display_state == DisplayState.UNAVAILABLE
    assert decision.click_action == ClickAction.NONE


# --- enable() / disable() ---


def test_disable_sets_hidden_true_in_place_and_preserves_other_keys(
    tmp_path: Path, monkeypatch
) -> None:
    """Set Hidden=true without changing other entry content."""
    path = _entry(tmp_path, monkeypatch, _WITH_COMMENTS_AND_EXTRA_KEYS)

    outcome, error = linux_autostart.disable()

    assert outcome == WriteOutcome.OK
    assert error is None
    text = path.read_text(encoding="utf-8")
    assert "Hidden=true" in text
    assert "X-Some-Other-Key=keep-me" in text
    assert "# a comment inside the group" in text
    assert "# a comment above the group" in text


def test_enable_sets_hidden_false_in_place_and_preserves_other_keys(
    tmp_path: Path, monkeypatch
) -> None:
    """Set Hidden=false without changing other entry content."""
    path = _entry(
        tmp_path,
        monkeypatch,
        _WITH_COMMENTS_AND_EXTRA_KEYS + "Hidden=true\n",
    )

    outcome, error = linux_autostart.enable()

    assert outcome == WriteOutcome.OK
    assert error is None
    text = path.read_text(encoding="utf-8")
    assert "Hidden=false" in text
    assert "Hidden=true" not in text
    assert "X-Some-Other-Key=keep-me" in text


def test_disable_reports_error_when_entry_disappears_before_write(
    tmp_path: Path, monkeypatch
) -> None:
    """Return an error when the entry cannot be read."""
    _entry(tmp_path, monkeypatch, None)

    outcome, error = linux_autostart.disable()

    assert outcome == WriteOutcome.ERROR
    assert error is not None


# --- create() ---


def test_create_writes_the_canonical_enabled_entry(tmp_path: Path, monkeypatch) -> None:
    """Create an enabled entry that launches with --no-browser."""
    path = _entry(tmp_path, monkeypatch, None)

    outcome, error = linux_autostart.create(exe_path=_EXE)

    assert outcome == WriteOutcome.OK
    assert error is None
    text = path.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in text
    assert f"Exec={_EXE} --no-browser" in text
    assert "Hidden" not in text


def test_create_makes_the_autostart_directory_if_missing(tmp_path: Path, monkeypatch) -> None:
    """Create the autostart directory when missing."""
    path = tmp_path / "does" / "not" / "exist" / "no.tip.tapmap.desktop"
    monkeypatch.setattr(linux_autostart, "_entry_path", lambda: path)

    outcome, _error = linux_autostart.create(exe_path=_EXE)

    assert outcome == WriteOutcome.OK
    assert path.exists()


# --- run_startup_setup() ---


def test_startup_setup_noop_for_source_run(tmp_path: Path, monkeypatch) -> None:
    """Do not read or write anything during a source run."""
    _entry(tmp_path, monkeypatch, None)

    linux_autostart.run_startup_setup(app_data_dir=tmp_path, exe_path=_EXE, is_frozen=False)

    assert marker.has_completed_setup(tmp_path) is False


def test_startup_setup_noop_once_marker_exists(tmp_path: Path, monkeypatch) -> None:
    """Do not read the entry once the setup marker exists."""
    marker.mark_setup_completed(tmp_path)

    def _fail():
        """Fail the test if called."""
        raise AssertionError("must not read once the marker exists")

    monkeypatch.setattr(linux_autostart, "_query_native_status", _fail)

    linux_autostart.run_startup_setup(app_data_dir=tmp_path, exe_path=_EXE, is_frozen=True)


def test_startup_setup_creates_entry_and_writes_marker_when_absent(
    tmp_path: Path, monkeypatch
) -> None:
    """Create the entry and marker when no entry exists."""
    path = _entry(tmp_path, monkeypatch, None)

    linux_autostart.run_startup_setup(app_data_dir=tmp_path, exe_path=_EXE, is_frozen=True)

    assert path.exists()
    assert marker.has_completed_setup(tmp_path) is True


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(_CANONICAL, id="enabled"),
        pytest.param(_CANONICAL + "Hidden=true\n", id="disabled"),
        pytest.param("not a desktop entry\n", id="malformed"),
    ],
)
def test_startup_setup_preserves_existing_entry_and_writes_marker(
    tmp_path: Path, monkeypatch, text: str
) -> None:
    """Preserve an existing entry and write only the marker."""
    path = _entry(tmp_path, monkeypatch, text)
    original = path.read_text(encoding="utf-8")

    linux_autostart.run_startup_setup(app_data_dir=tmp_path, exe_path=_EXE, is_frozen=True)

    assert path.read_text(encoding="utf-8") == original
    assert marker.has_completed_setup(tmp_path) is True


def test_startup_setup_does_not_write_marker_when_creation_fails(
    tmp_path: Path, monkeypatch
) -> None:
    """Keep the marker absent when initial entry creation fails."""
    _entry(tmp_path, monkeypatch, None)

    def _fail(*, exe_path):
        """Simulate a failed entry creation."""
        return WriteOutcome.ERROR, "boom"

    monkeypatch.setattr(linux_autostart, "create", _fail)

    linux_autostart.run_startup_setup(app_data_dir=tmp_path, exe_path=_EXE, is_frozen=True)

    assert marker.has_completed_setup(tmp_path) is False


def test_startup_setup_does_nothing_when_entry_is_unreadable(tmp_path: Path, monkeypatch) -> None:
    """Make no changes when the entry cannot be read."""

    class _UnreadablePath(Path):
        def is_file(self):
            """Raise OSError instead of reporting whether the path is a file."""
            raise OSError("denied")

    monkeypatch.setattr(linux_autostart, "_entry_path", lambda: _UnreadablePath(tmp_path / "x"))

    linux_autostart.run_startup_setup(app_data_dir=tmp_path, exe_path=_EXE, is_frozen=True)

    assert marker.has_completed_setup(tmp_path) is False
