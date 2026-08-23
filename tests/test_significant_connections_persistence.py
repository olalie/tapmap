"""Tests for Significant Connections persistence robustness."""

from __future__ import annotations

import json
from pathlib import Path

from tapmap.significant_connections_persistence import (
    load_significant_connections,
    save_significant_connections,
)


def test_save_and_reload_preserves_order_and_content(tmp_path: Path) -> None:
    """Saving and reloading must preserve event order and content exactly."""
    path = tmp_path / "significant_connections.json"
    events = [
        {"timestamp": "2026-08-01T00:00:00", "reasons": ["new_app"], "ip": "1.1.1.1"},
        {"timestamp": "2026-08-02T00:00:00", "reasons": ["new_country"], "ip": "2.2.2.2"},
    ]

    save_significant_connections(path, events)
    loaded = load_significant_connections(path)

    assert loaded == events


def test_load_missing_file_returns_empty_list(tmp_path: Path) -> None:
    """A missing file returns an empty list rather than raising."""
    path = tmp_path / "does_not_exist.json"

    assert load_significant_connections(path) == []


def test_load_corrupt_json_returns_empty_list(tmp_path: Path) -> None:
    """Corrupt JSON must not crash; loading falls back to an empty list."""
    path = tmp_path / "significant_connections.json"
    path.write_text("not valid json", encoding="utf-8")

    assert load_significant_connections(path) == []


def test_load_drops_malformed_records_but_keeps_valid_ones(tmp_path: Path) -> None:
    """Non-dict entries in 'events' are dropped; well-formed entries are kept."""
    path = tmp_path / "significant_connections.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "events": [
                    {"timestamp": "t", "reasons": ["new_app"]},
                    "not-a-dict",
                    123,
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = load_significant_connections(path)

    assert loaded == [{"timestamp": "t", "reasons": ["new_app"]}]


def test_load_wrong_events_type_returns_empty_list(tmp_path: Path) -> None:
    """A non-list 'events' value falls back to an empty list."""
    path = tmp_path / "significant_connections.json"
    path.write_text(json.dumps({"events": "not-a-list"}), encoding="utf-8")

    assert load_significant_connections(path) == []
