"""Preserve corrupt history files under timestamped backup names."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_CORRUPT_BACKUPS = 3


def backup_corrupt_file(path: Path, now: datetime) -> Path:
    """Rename path to a timestamped corrupt-file backup and return the backup path.

    Keep at most MAX_CORRUPT_BACKUPS backups per history file; delete the oldest.
    A failed deletion is logged and does not fail the backup.

    Raises:
        FileExistsError: If the backup name is already taken.
        OSError: If path cannot be renamed.
    """
    backup_path = path.with_name(f"{path.stem}.corrupt-{now:%Y%m%d-%H%M%S-%f}{path.suffix}")
    # Path.rename replaces an existing file on POSIX.
    if backup_path.exists():
        raise FileExistsError(f"corrupt-file backup already exists: {backup_path}")
    path.rename(backup_path)

    backups = sorted(path.parent.glob(f"{path.stem}.corrupt-*{path.suffix}"))
    for old_backup in backups[:-MAX_CORRUPT_BACKUPS]:
        try:
            old_backup.unlink()
        except OSError as exc:
            logger.warning("Unable to delete old corrupt-file backup %s: %s", old_backup, exc)

    return backup_path
