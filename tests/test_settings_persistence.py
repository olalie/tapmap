"""Tests for settings persistence robustness."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from tapmap.settings_persistence import Settings, load_settings, save_settings


def test_load_settings_missing_file_returns_defaults(tmp_path: Path) -> None:
    """Return default settings when the file does not exist."""
    path = tmp_path / "settings.json"

    result = load_settings(path)

    assert result == Settings(
        version=1, insights_panel=True, technical_details=False, desktop_notifications=True
    )


def test_load_settings_corrupt_json_returns_defaults(tmp_path: Path) -> None:
    """Corrupt JSON must not crash; settings must fall back to defaults."""
    path = tmp_path / "settings.json"
    path.write_text("not valid json", encoding="utf-8")

    result = load_settings(path)

    assert result == Settings()


def test_load_settings_partial_data_fills_defaults(tmp_path: Path) -> None:
    """Missing keys in the JSON file are filled in with defaults."""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"technical_details": True}), encoding="utf-8")

    result = load_settings(path)

    assert result == Settings(
        version=1, insights_panel=True, technical_details=True, desktop_notifications=True
    )


def test_load_settings_desktop_notifications_disabled_is_preserved(tmp_path: Path) -> None:
    """A persisted desktop_notifications=False is not overwritten by the default."""
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"desktop_notifications": False}), encoding="utf-8")

    result = load_settings(path)

    assert result.desktop_notifications is False


def test_load_settings_ignores_unknown_keys(tmp_path: Path) -> None:
    """Unknown/legacy keys in the JSON file are ignored."""
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "insights_panel": False,
                "technical_details": True,
                "legacy_field": "should_be_ignored",
            }
        ),
        encoding="utf-8",
    )

    result = load_settings(path)

    assert result == Settings(
        version=1, insights_panel=False, technical_details=True, desktop_notifications=True
    )


def test_save_and_load_settings_roundtrip(tmp_path: Path) -> None:
    """Saving and reloading settings must preserve all values exactly."""
    path = tmp_path / "settings.json"
    settings = Settings(
        version=1, insights_panel=False, technical_details=True, desktop_notifications=False
    )

    save_settings(path, settings)
    result = load_settings(path)

    assert result == settings


def test_save_settings_writes_exact_expected_shape(tmp_path: Path) -> None:
    """The saved JSON file matches the exact expected structure."""
    path = tmp_path / "settings.json"
    settings = Settings(
        version=1, insights_panel=True, technical_details=False, desktop_notifications=True
    )

    save_settings(path, settings)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data == {
        "version": 1,
        "insights_panel": True,
        "technical_details": False,
        "desktop_notifications": True,
    }


def test_settings_is_frozen() -> None:
    """Settings instances must be immutable."""
    settings = Settings()

    with pytest.raises(FrozenInstanceError):
        settings.technical_details = True