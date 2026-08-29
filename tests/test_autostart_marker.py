"""Test the one-time autostart setup marker file."""

from __future__ import annotations

from pathlib import Path

from tapmap.autostart import marker


def test_marker_round_trip(tmp_path: Path) -> None:
    """Marking setup complete creates a zero-byte marker that has_completed_setup() reflects."""
    assert marker.has_completed_setup(tmp_path) is False

    marker.mark_setup_completed(tmp_path)

    assert marker.has_completed_setup(tmp_path) is True
    assert marker.marker_path(tmp_path).read_bytes() == b""


def test_mark_setup_completed_is_idempotent(tmp_path: Path) -> None:
    """Marking setup complete twice does not raise."""
    marker.mark_setup_completed(tmp_path)
    marker.mark_setup_completed(tmp_path)

    assert marker.has_completed_setup(tmp_path) is True
