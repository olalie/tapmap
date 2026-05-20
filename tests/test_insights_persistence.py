"""Tests for insights persistence robustness and the single-instance lock guard."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import unittest.mock
from pathlib import Path

import pytest

from tapmap.app import TapMap


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


_EMPTY: dict = {"countries": {}, "providers": {}, "ports": {}, "applications": {}}


def _bare_app(tmp_path: Path) -> TapMap:
    """Return a TapMap instance with only the attributes needed for method-level tests."""
    app = object.__new__(TapMap)
    app.logger = logging.getLogger("test")
    app.insights = {}
    app.insights_path = tmp_path / "insights.json"
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


# --- _acquire_lock: running PID blocks startup ---


def test_acquire_lock_blocks_when_pid_running(tmp_path: Path) -> None:
    """A lock file with a live foreign PID must cause sys.exit(1)."""
    app = _bare_app(tmp_path)
    fake_pid = 99999
    app._lock_path.write_text(str(fake_pid), encoding="utf-8")
    with (
        unittest.mock.patch("tapmap.app.psutil.pid_exists", return_value=True),
        pytest.raises(SystemExit) as exc_info,
    ):
        app._acquire_lock()
    assert exc_info.value.code == 1


# --- _acquire_lock: stale lock is replaced ---


def test_acquire_lock_replaces_stale_lock(tmp_path: Path) -> None:
    """A lock file whose PID is no longer running must be overwritten silently."""
    app = _bare_app(tmp_path)
    app._lock_path.write_text("99999", encoding="utf-8")
    with unittest.mock.patch("tapmap.app.psutil.pid_exists", return_value=False):
        app._acquire_lock()  # must not raise
    assert app._lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())
