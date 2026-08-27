"""Tests for insights persistence robustness and the single-instance lock guard."""

from __future__ import annotations

import contextlib
import json
import logging
import unittest.mock
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import psutil
import pytest

from tapmap.app import TapMap
from tapmap.settings_persistence import Settings
from tapmap.state.insights_state import CURRENT_SCHEMA_VERSION, InsightsState
from tapmap.state.significant_connections import SignificantConnections


def test_failed_save_does_not_corrupt_state(tmp_path: Path) -> None:
    """A failed save does not corrupt or clear in-memory state, for either history file."""
    app = _bare_app(tmp_path)
    app.insights_state = InsightsState(
        version=CURRENT_SCHEMA_VERSION,
        insights={"countries": {"NO": 1}, "providers": {}, "ports": {}, "applications": {}},
        verification_failed={},
    )
    app.significant_connections = SignificantConnections([{"timestamp": "t", "reasons": ["x"]}])
    # Simulate save failure by patching Path.open to raise OSError
    with (
        unittest.mock.patch.object(Path, "open", side_effect=OSError("disk full")),
        contextlib.suppress(OSError),
    ):
        app._save_history()
    # State should be unchanged
    assert app.insights_state.insights == {
        "countries": {"NO": 1},
        "providers": {},
        "ports": {},
        "applications": {},
    }
    assert app.significant_connections.items == [{"timestamp": "t", "reasons": ["x"]}]


def test_save_history_isolates_failure_per_file(tmp_path: Path) -> None:
    """A failing insights save must not prevent Significant Connections from being saved."""
    app = _bare_app(tmp_path)
    app.insights_state = InsightsState(
        version=CURRENT_SCHEMA_VERSION,
        insights=_EMPTY,
        verification_failed={},
    )
    app.significant_connections = SignificantConnections([{"timestamp": "t", "reasons": ["x"]}])

    real_open = Path.open

    def _flaky_open(self: Path, *args: object, **kwargs: object):
        if self.name.startswith("insights"):
            raise OSError("disk full")
        return real_open(self, *args, **kwargs)

    with (
        unittest.mock.patch.object(Path, "open", _flaky_open),
        contextlib.suppress(OSError),
    ):
        app._save_history()

    assert not app.insights_path.exists()
    assert app.significant_connections_path.exists()


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
    app.runtime = SimpleNamespace(is_docker=False, server_host="127.0.0.1", server_port=8050)
    app.insights_state = InsightsState(
        version=CURRENT_SCHEMA_VERSION, insights={}, verification_failed={}
    )
    app.insights_path = tmp_path / "insights.json"
    app.significant_connections = SignificantConnections([])
    app.significant_connections_path = tmp_path / "significant_connections.json"
    app.settings = Settings()
    app.settings_path = tmp_path / "settings.json"
    app._lock_path = tmp_path / "tapmap.lock"
    return app


# --- _load_history: corrupt JSON ---


def test_load_history_corrupt_json_fallback(tmp_path: Path) -> None:
    """Corrupt JSON must not crash; insights must become the empty structure."""
    app = _bare_app(tmp_path)
    app.insights_path.write_text("not valid json", encoding="utf-8")
    app._load_history()
    assert app.insights_state.insights == _EMPTY
    assert app.insights_state.verification_failed == {}
    assert app.significant_connections.items == []


# --- _load_history: unexpected structure ---


def test_load_history_wrong_structure_fallback(tmp_path: Path) -> None:
    """A non-dict 'insights' value must fall back to the empty structure."""
    app = _bare_app(tmp_path)
    app.insights_path.write_text(json.dumps({"insights": ["not", "a", "dict"]}), encoding="utf-8")
    app._load_history()
    assert app.insights_state.insights == _EMPTY


# --- _load_history: unknown top-level keys are discarded ---


def test_load_history_strips_unknown_keys(tmp_path: Path) -> None:
    """Only the four recognised Insights keys should be kept; unknown keys are discarded."""
    app = _bare_app(tmp_path)
    data = {
        "version": CURRENT_SCHEMA_VERSION,
        "insights": {
            "countries": {"US": 1},
            "providers": {},
            "ports": {},
            "applications": {},
            "legacy_field": {"should": "be_removed"},
        },
    }
    app.insights_path.write_text(json.dumps(data), encoding="utf-8")
    app._load_history()
    assert set(app.insights_state.insights.keys()) == {
        "countries",
        "providers",
        "ports",
        "applications",
    }
    assert "legacy_field" not in app.insights_state.insights
    assert app.insights_state.insights["countries"] == {"US": 1}


# --- _save_history / _load_history: roundtrip ---


def test_save_and_reload_preserves_data(tmp_path: Path) -> None:
    """Saving and reloading both history files must preserve all data exactly."""
    app = _bare_app(tmp_path)
    app.insights_state = InsightsState(
        version=CURRENT_SCHEMA_VERSION,
        insights={
            "countries": {"DE": 3},
            "providers": {"AS1234": 1},
            "ports": {"443": 5},
            "applications": {"curl": 2},
        },
        verification_failed={"BadApp": 738000},
    )
    app.significant_connections = SignificantConnections(
        [{"timestamp": "2026-08-01T00:00:00", "reasons": ["new_app"]}]
    )
    app._save_history()

    app.insights_state = InsightsState(version=0, insights={}, verification_failed={})
    app.significant_connections = SignificantConnections([])
    app._load_history()

    assert app.insights_state.insights == {
        "countries": {"DE": 3},
        "providers": {"AS1234": 1},
        "ports": {"443": 5},
        "applications": {"curl": 2},
    }
    assert app.insights_state.verification_failed == {"BadApp": 738000}
    assert app.insights_state.version == CURRENT_SCHEMA_VERSION
    assert app.significant_connections.items == [
        {"timestamp": "2026-08-01T00:00:00", "reasons": ["new_app"]}
    ]


# --- _load_history: applications-only migration ---


def test_load_history_migrates_pre_v2_applications_only(tmp_path: Path) -> None:
    """A file with no version marker resets applications but preserves other dimensions."""
    app = _bare_app(tmp_path)
    data = {
        "insights": {
            "countries": {"US": 1},
            "providers": {"AS15169": 1},
            "ports": {"443": 1},
            "applications": {"chrome.exe": {"l": 738000, "m": 1}},
        }
    }
    app.insights_path.write_text(json.dumps(data), encoding="utf-8")
    app._load_history()

    assert app.insights_state.insights["applications"] == {}
    assert app.insights_state.insights["countries"] == {"US": 1}
    assert app.insights_state.insights["providers"] == {"AS15169": 1}
    assert app.insights_state.insights["ports"] == {"443": 1}
    assert app.insights_state.version == CURRENT_SCHEMA_VERSION


def test_load_history_does_not_migrate_current_version(tmp_path: Path) -> None:
    """A file already at the current schema version keeps its applications history."""
    app = _bare_app(tmp_path)
    data = {
        "version": CURRENT_SCHEMA_VERSION,
        "insights": {
            "countries": {},
            "providers": {},
            "ports": {},
            "applications": {"Google Chrome": {"l": 738000, "m": 1}},
        },
        "verification_failed": {},
    }
    app.insights_path.write_text(json.dumps(data), encoding="utf-8")
    app._load_history()

    assert app.insights_state.insights["applications"] == {"Google Chrome": {"l": 738000, "m": 1}}


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
    """Exit when the lock belongs to a currently running TapMap instance, opening its browser."""
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
        patch("tapmap.app.webbrowser.open") as mock_open,
        pytest.raises(SystemExit) as exc_info,
    ):
        app._acquire_lock()

    assert exc_info.value.code == 1
    mock_open.assert_called_once_with("http://127.0.0.1:8050/", new=2)


def test_acquire_lock_does_not_open_browser_for_docker(tmp_path: Path) -> None:
    """Docker never opens a browser, even when another instance is detected."""
    app = _bare_app(tmp_path)
    app.runtime = SimpleNamespace(is_docker=True, server_host="0.0.0.0", server_port=8050)

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
        patch("tapmap.app.webbrowser.open") as mock_open,
        pytest.raises(SystemExit),
    ):
        app._acquire_lock()

    mock_open.assert_not_called()


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
