"""Manage Linux autostart using the XDG `Hidden` key.

Other desktop-specific autostart settings are left unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final

from tapmap.state.autostart import (
    AutostartDecision,
    LinuxAutostartState,
    NativeLinuxAutostartStatus,
    WriteOutcome,
    decide_linux_autostart_display,
)

from . import marker

logger = logging.getLogger(__name__)

_ENTRY_RELATIVE_PATH: Final = Path(".config") / "autostart" / "no.tip.tapmap.desktop"
_GROUP_HEADER: Final[str] = "[Desktop Entry]"
_HIDDEN_KEY: Final[str] = "Hidden"

_UNREADABLE_STATUS: Final[NativeLinuxAutostartStatus] = NativeLinuxAutostartStatus(
    queryable=False, state=None
)


class LinuxAutostartError(Exception):
    """Raised when the XDG autostart entry cannot be written."""


def _entry_path() -> Path:
    """Return the path to TapMap's XDG autostart entry."""
    return Path.home() / _ENTRY_RELATIVE_PATH


def _find_group_bounds(lines: list[str]) -> tuple[int, int] | None:
    """Return the line bounds of the `[Desktop Entry]` group."""
    start = None
    for index, line in enumerate(lines):
        if line.strip() == _GROUP_HEADER:
            start = index + 1
            break
    if start is None:
        return None

    end = len(lines)
    for index in range(start, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = index
            break
    return start, end


def _read_hidden_value(lines: list[str], bounds: tuple[int, int]) -> str | None:
    """Return the first `Hidden` value in the group, or None if absent."""
    start, end = bounds
    for index in range(start, end):
        stripped = lines[index].strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() == _HIDDEN_KEY:
            return value.strip()
    return None


def _query_native_status() -> NativeLinuxAutostartStatus:
    """Return the current parsed state of the XDG autostart entry."""
    path = _entry_path()

    try:
        exists = path.is_file()
    except OSError:
        return _UNREADABLE_STATUS

    if not exists:
        return NativeLinuxAutostartStatus(queryable=True, state=LinuxAutostartState.ABSENT)

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return _UNREADABLE_STATUS
    except UnicodeDecodeError:
        return NativeLinuxAutostartStatus(queryable=True, state=LinuxAutostartState.MALFORMED)

    lines = text.splitlines()
    bounds = _find_group_bounds(lines)
    if bounds is None:
        return NativeLinuxAutostartStatus(queryable=True, state=LinuxAutostartState.MALFORMED)

    hidden_value = _read_hidden_value(lines, bounds)

    if hidden_value is None or hidden_value == "false":
        return NativeLinuxAutostartStatus(queryable=True, state=LinuxAutostartState.ENABLED)
    if hidden_value == "true":
        return NativeLinuxAutostartStatus(queryable=True, state=LinuxAutostartState.DISABLED)

    return NativeLinuxAutostartStatus(queryable=True, state=LinuxAutostartState.MALFORMED)


def _write_hidden_value(*, value: str) -> None:
    """Set `Hidden` on the existing entry without changing other keys."""
    path = _entry_path()
    lines = path.read_text(encoding="utf-8").splitlines()
    bounds = _find_group_bounds(lines)
    if bounds is None:
        raise LinuxAutostartError("No [Desktop Entry] group found; cannot write Hidden.")
    start, end = bounds

    for index in range(start, end):
        stripped = lines[index].strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, _ = stripped.partition("=")
        if key.strip() == _HIDDEN_KEY:
            lines[index] = f"{_HIDDEN_KEY}={value}"
            break
    else:
        lines.insert(start, f"{_HIDDEN_KEY}={value}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _canonical_entry_text(*, exe_path: str) -> str:
    """Return a new enabled TapMap autostart entry."""
    return (
        f"{_GROUP_HEADER}\n"
        "Type=Application\n"
        "Name=TapMap\n"
        f"Exec={exe_path} --no-browser\n"
        "Terminal=false\n"
    )


def query_display_state(*, is_frozen: bool) -> AutostartDecision:
    """Return the state and action for the autostart control."""
    if not is_frozen:
        # Source runs must not query the XDG autostart entry.
        return decide_linux_autostart_display(status=_UNREADABLE_STATUS, is_source_run=True)

    status = _query_native_status()
    return decide_linux_autostart_display(status=status, is_source_run=False)


def enable() -> tuple[WriteOutcome, str | None]:
    """Enable autostart by setting Hidden=false on the existing entry."""
    try:
        _write_hidden_value(value="false")
    except (OSError, LinuxAutostartError) as exc:
        return WriteOutcome.ERROR, str(exc)
    return WriteOutcome.OK, None


def disable() -> tuple[WriteOutcome, str | None]:
    """Disable autostart by setting Hidden=true on the existing entry."""
    try:
        _write_hidden_value(value="true")
    except (OSError, LinuxAutostartError) as exc:
        return WriteOutcome.ERROR, str(exc)
    return WriteOutcome.OK, None


def create(*, exe_path: str) -> tuple[WriteOutcome, str | None]:
    """Create an enabled TapMap autostart entry."""
    path = _entry_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_canonical_entry_text(exe_path=exe_path), encoding="utf-8")
    except OSError as exc:
        return WriteOutcome.ERROR, str(exc)
    return WriteOutcome.OK, None


def run_startup_setup(*, app_data_dir: Path, exe_path: str, is_frozen: bool) -> None:
    """Set up autostart on first launch."""
    if not is_frozen:
        return
    if marker.has_completed_setup(app_data_dir):
        return

    status = _query_native_status()

    if not status.queryable:
        logger.warning("Unable to read the XDG autostart entry for initial setup.")
        return

    if status.state != LinuxAutostartState.ABSENT:
        # Preserve any existing entry, including malformed entries.
        marker.mark_setup_completed(app_data_dir)
        return

    outcome, error = create(exe_path=exe_path)
    if outcome == WriteOutcome.OK:
        marker.mark_setup_completed(app_data_dir)
    else:
        logger.warning("Unable to create the initial TapMap autostart entry: %s", error)
