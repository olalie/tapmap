"""The one-time autostart setup marker.

Not current autostart state - only the native OS mechanism is.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

MARKER_FILENAME: Final[str] = "autostart_setup_completed.marker"


def marker_path(app_data_dir: Path) -> Path:
    """Return the marker file path for app_data_dir."""
    return app_data_dir / MARKER_FILENAME


def has_completed_setup(app_data_dir: Path) -> bool:
    """Return True if initial autostart setup has already been handled."""
    return marker_path(app_data_dir).exists()


def mark_setup_completed(app_data_dir: Path) -> None:
    """Record that initial autostart setup has been handled. Idempotent."""
    marker_path(app_data_dir).touch(exist_ok=True)
