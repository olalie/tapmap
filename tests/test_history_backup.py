"""Tests for corrupt history file backups."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pytest

from tapmap.history_backup import backup_corrupt_file

_NOW = datetime(2026, 11, 8, 15, 30, 0, 123456)


def test_backup_moves_file_to_timestamped_name(tmp_path: Path) -> None:
    """Move the file to a microsecond-timestamped backup with its content intact."""
    path = tmp_path / "insights.json"
    path.write_text("corrupt", encoding="utf-8")

    backup_path = backup_corrupt_file(path, _NOW)

    assert backup_path.name == "insights.corrupt-20261108-153000-123456.json"
    assert backup_path.read_text(encoding="utf-8") == "corrupt"
    assert not path.exists()


def test_backup_keeps_newest_three(tmp_path: Path) -> None:
    """Delete backups older than the newest three."""
    path = tmp_path / "insights.json"
    path.write_text("corrupt", encoding="utf-8")
    old_names = [f"insights.corrupt-2020010{day}-000000-000000.json" for day in (1, 2, 3)]
    for name in old_names:
        (tmp_path / name).write_text("old", encoding="utf-8")

    backup_path = backup_corrupt_file(path, _NOW)

    assert sorted(p.name for p in tmp_path.glob("insights.corrupt-*.json")) == [
        *old_names[1:],
        backup_path.name,
    ]


def test_backup_refuses_existing_backup_name(tmp_path: Path) -> None:
    """Raise FileExistsError and leave both files unchanged on a name collision."""
    path = tmp_path / "insights.json"
    path.write_text("corrupt", encoding="utf-8")
    existing = tmp_path / "insights.corrupt-20261108-153000-123456.json"
    existing.write_text("earlier backup", encoding="utf-8")

    with pytest.raises(FileExistsError):
        backup_corrupt_file(path, _NOW)

    assert existing.read_text(encoding="utf-8") == "earlier backup"
    assert path.read_text(encoding="utf-8") == "corrupt"


def test_backup_logs_failed_deletion_of_old_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Return the backup and log a warning when an old backup cannot be deleted."""
    path = tmp_path / "insights.json"
    path.write_text("corrupt", encoding="utf-8")
    for day in (1, 2, 3):
        (tmp_path / f"insights.corrupt-2020010{day}-000000-000000.json").write_text("old")

    def _raise_os_error(_self: Path, missing_ok: bool = False) -> None:
        """Raise PermissionError for any path."""
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "unlink", _raise_os_error)

    with caplog.at_level(logging.WARNING, logger="tapmap.history_backup"):
        backup_path = backup_corrupt_file(path, _NOW)

    assert backup_path.read_text(encoding="utf-8") == "corrupt"
    assert "Unable to delete old corrupt-file backup" in caplog.text
