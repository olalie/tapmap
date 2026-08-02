"""Tests for insights persistence robustness and the single-instance lock guard."""

from __future__ import annotations

import contextlib
import json
import logging
import unittest.mock
from pathlib import Path
from unittest.mock import MagicMock, patch

import psutil
import pytest

from tapmap.app import TapMap
from tapmap.settings_persistence import Settings


def test_failed_save_does_not_corrupt_state(tmp_path: Path) -> None:
    """A failed save does not corrupt or clear in-memory state."""
    app = _bare_app(tmp_path)
    app.insights = {
        "countries": {"NO": 1},
        "providers": {},
        "ports": {},
        "applications": {},
    }
    # Simulate save failure by patching Path.open to raise OSError
    with (
        unittest.mock.patch.object(Path, "open", side_effect=OSError("disk full")),
        contextlib.suppress(OSError),
    ):
        app._save_insights()
    # State should be unchanged
    assert app.insights == {
        "countries": {"NO": 1},
        "providers": {},
        "ports": {},
        "applications": {},
    }


def test_failed_save_settings_does_not_corrupt_state(tmp_path: Path) -> None:
    """A failed settings save does not corrupt or clear in-memory state."""
    app = _bare_app(tmp_path)
    app.settings = Settings(version=1, insights_panel=False, technical_details=True)
    # Simulate save failure by patching Path.open to raise OSError
    with (
        unittest.mock.patch.object(Path, "open", side_effect=OSError("disk full")),
        contextlib.suppress(OSError),
    ):
        app._save_settings()
    # State should be unchanged
    assert app.settings == Settings(version=1, insights_panel=False, technical_details=True)


_EMPTY: dict = {"countries": {}, "providers": {}, "ports": {}, "applications": {}}


def _bare_app(tmp_path: Path) -> TapMap:
    """Return a TapMap instance with only the attributes needed for method-level tests."""
    app = object.__new__(TapMap)
    app.logger = logging.getLogger("test")
    app.insights = {}
    app.insights_path = tmp_path / "insights.json"
    app.settings = Settings()
    app.settings_path = tmp_path / "settings.json"
    app._lock_path = tmp_path / "tapmap.lock"
    return app


# --- _load_insights: corrupt JSON ---


def test_load_insights_corrupt_json_fallback(tmp_path: Path) -> None:
    """Corrupt JSON must not crash; insights must become the empty structure."""
    app = _bare_app(tmp_path)
    app.insights_path.write_text("not valid json", encoding="utf-8")
    app._load_insights()
    assert app.insights == _EMPTY


# --- _load_insights: unexpected structure ---


def test_load_insights_wrong_structure_fallback(tmp_path: Path) -> None:
    """A non-dict 'insights' value must fall back to the empty structure."""
    app = _bare_app(tmp_path)
    app.insights_path.write_text(json.dumps({"insights": ["not", "a", "dict"]}), encoding="utf-8")
    app._load_insights()
    assert app.insights == _EMPTY


# --- _load_insights: unknown top-level keys are discarded ---


def test_load_insights_strips_unknown_keys(tmp_path: Path) -> None:
    """Only the four recognised keys should be kept; unknown keys are discarded."""
    app = _bare_app(tmp_path)
    data = {
        "insights": {
            "countries": {"US": 1},
            "providers": {},
            "ports": {},
            "applications": {},
            "legacy_field": {"should": "be_removed"},
        }
    }
    app.insights_path.write_text(json.dumps(data), encoding="utf-8")
    app._load_insights()
    assert set(app.insights.keys()) == {"countries", "providers", "ports", "applications"}
    assert "legacy_field" not in app.insights
    assert app.insights["countries"] == {"US": 1}


# --- _save_insights / _load_insights: roundtrip ---


def test_save_and_reload_preserves_data(tmp_path: Path) -> None:
    """Saving and reloading insights must preserve all data exactly."""
    app = _bare_app(tmp_path)
    app.insights = {
        "countries": {"DE": 3},
        "providers": {"AS1234": 1},
        "ports": {"443": 5},
        "applications": {"curl": 2},
    }
    app._save_insights()
    app.insights = {}
    app._load_insights()
    assert app.insights == {
        "countries": {"DE": 3},
        "providers": {"AS1234": 1},
        "ports": {"443": 5},
        "applications": {"curl": 2},
    }

# --- _acquire_lock ---


def test_acquire_lock_without_existing_lock(tmp_path: Path) -> None:
    """Create a new lock file when none exists."""
    app = _bare_app(tmp_path)

    current = MagicMock()
    current.pid = 123
    current.create_time.return_value = 1.23

    with patch("psutil.Process", return_value=current):
        app._acquire_lock()

    lock = json.loads(app._lock_path.read_text())

    assert lock["pid"] == 123
    assert lock["create_time"] == 1.23


def test_acquire_lock_exits_when_same_process_running(tmp_path: Path) -> None:
    """Exit when the lock belongs to a currently running TapMap instance."""
    app = _bare_app(tmp_path)

    app._lock_path.write_text(
        json.dumps(
            {
                "pid": 123,
                "create_time": 1.23,
            }
        )
    )

    running = MagicMock()
    running.pid = 123
    running.create_time.return_value = 1.23

    with (
        patch("psutil.Process", return_value=running),
        pytest.raises(SystemExit) as exc_info,
    ):
        app._acquire_lock()

    assert exc_info.value.code == 1


def test_acquire_lock_replaces_stale_lock(tmp_path: Path) -> None:
    """Replace a lock whose PID has been reused."""
    app = _bare_app(tmp_path)

    app._lock_path.write_text(
        json.dumps(
            {
                "pid": 123,
                "create_time": 1.23,
            }
        )
    )

    running = MagicMock()
    running.pid = 123
    running.create_time.return_value = 9.99

    current = MagicMock()
    current.pid = 456
    current.create_time.return_value = 5.55

    with patch("psutil.Process", side_effect=[running, current]):
        app._acquire_lock()

    lock = json.loads(app._lock_path.read_text())

    assert lock["pid"] == 456
    assert lock["create_time"] == 5.55


def test_acquire_lock_replaces_missing_process(tmp_path: Path) -> None:
    """Replace a lock whose process no longer exists."""
    app = _bare_app(tmp_path)

    app._lock_path.write_text(
        json.dumps(
            {
                "pid": 123,
                "create_time": 1.23,
            }
        )
    )

    current = MagicMock()
    current.pid = 456
    current.create_time.return_value = 5.55

    with patch(
        "psutil.Process",
        side_effect=[
            psutil.NoSuchProcess(123),
            current,
        ],
    ):
        app._acquire_lock()

    lock = json.loads(app._lock_path.read_text())

    assert lock["pid"] == 456
    assert lock["create_time"] == 5.55
