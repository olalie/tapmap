"""Tests for runtime location override parsing."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from tapmap.runtime import (
    _get_cache_retention_min,
    _get_launch_browser,
    _get_location_override,
)


class TestGetLocationOverride:
    """Test _get_location_override() env var parser."""

    def test_both_valid_coordinates(self) -> None:
        """Valid positive coordinates return tuple."""
        with patch.dict(os.environ, {"TAPMAP_LON": "10.5", "TAPMAP_LAT": "50.2"}, clear=True):
            result = _get_location_override()
            assert result == (10.5, 50.2)

    def test_both_valid_negative_coordinates(self) -> None:
        """Valid negative coordinates return tuple."""
        with patch.dict(os.environ, {"TAPMAP_LON": "-74.0", "TAPMAP_LAT": "-33.9"}, clear=True):
            result = _get_location_override()
            assert result == (-74.0, -33.9)

    @pytest.mark.parametrize("env", [
        {"TAPMAP_LAT": "50.2"},
        {"TAPMAP_LON": "10.5"},
        {},
    ])
    def test_missing_pair_returns_none(self, env: dict[str, str]) -> None:
        """Missing lon/lat pair returns None."""
        with patch.dict(os.environ, env, clear=True):
            result = _get_location_override()
            assert result is None

    @pytest.mark.parametrize("lon,lat", [
        ("invalid", "50.2"),
        ("abc", "50.2"),
        ("12.34.56", "50.2"),
        ("10.5", "invalid"),
        ("10.5", "xyz"),
        ("10.5", "90.1.2"),
    ])
    def test_invalid_float_returns_none(self, lon: str, lat: str) -> None:
        """Invalid float input in either var returns None."""
        with patch.dict(os.environ, {"TAPMAP_LON": lon, "TAPMAP_LAT": lat}, clear=True):
            result = _get_location_override()
            assert result is None

    @pytest.mark.parametrize("lon,lat", [
        ("-180.1", "50"),
        ("-200", "50"),
        ("180.1", "50"),
        ("200", "50"),
        ("10", "-90.1"),
        ("10", "-100"),
        ("10", "90.1"),
        ("10", "100"),
    ])
    def test_out_of_range_returns_none(self, lon: str, lat: str) -> None:
        """Out-of-range lon/lat returns None."""
        with patch.dict(os.environ, {"TAPMAP_LON": lon, "TAPMAP_LAT": lat}, clear=True):
            result = _get_location_override()
            assert result is None

    @pytest.mark.parametrize("lon,lat", [
        ("-180", "0"),
        ("180", "0"),
        ("0", "-90"),
        ("0", "90"),
    ])
    def test_boundary_values_return_tuple(self, lon: str, lat: str) -> None:
        """Boundary lon/lat values are accepted."""
        with patch.dict(os.environ, {"TAPMAP_LON": lon, "TAPMAP_LAT": lat}, clear=True):
            result = _get_location_override()
            assert result == (float(lon), float(lat))

    @pytest.mark.parametrize("lon,lat", [
        ("", "50"),
        ("10", ""),
        ("   ", "50"),
        ("10", "   "),
    ])
    def test_empty_or_whitespace_returns_none(self, lon: str, lat: str) -> None:
        """Empty or whitespace-only env vars return None."""
        with patch.dict(os.environ, {"TAPMAP_LON": lon, "TAPMAP_LAT": lat}, clear=True):
            result = _get_location_override()
            assert result is None

    def test_scientific_notation(self) -> None:
        """Scientific notation accepted as valid float."""
        with patch.dict(os.environ, {"TAPMAP_LON": "1e1", "TAPMAP_LAT": "5e1"}, clear=True):
            result = _get_location_override()
            assert result == (10.0, 50.0)


class TestGetLaunchBrowser:
    """Test _get_launch_browser() env var parser."""

    def test_default_returns_config(self) -> None:
        """Missing env var returns config default."""
        with patch.dict(os.environ, {}, clear=True):
            assert _get_launch_browser() is True

    @pytest.mark.parametrize("value", ["1", "true", "yes", "on"])
    def test_true_values(self, value: str) -> None:
        """Accepted true values return True."""
        with patch.dict(os.environ, {"TAPMAP_LAUNCH_BROWSER": value}, clear=True):
            assert _get_launch_browser() is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "off"])
    def test_false_values(self, value: str) -> None:
        """Accepted false values return False."""
        with patch.dict(os.environ, {"TAPMAP_LAUNCH_BROWSER": value}, clear=True):
            assert _get_launch_browser() is False

    def test_invalid_value_returns_config_default(self) -> None:
        """Invalid value falls back to config default."""
        with patch.dict(os.environ, {"TAPMAP_LAUNCH_BROWSER": "banana"}, clear=True):
            assert _get_launch_browser() is True


class TestGetCacheRetentionMin:
    """Test _get_cache_retention_min() env var parser."""

    def test_default_returns_config(self) -> None:
        """Missing env var returns config default."""
        with patch.dict(os.environ, {}, clear=True):
            assert _get_cache_retention_min() == 0

    def test_valid_value(self) -> None:
        """Positive integer is accepted."""
        with patch.dict(os.environ, {"TAPMAP_CACHE_RETENTION_MIN": "15"}, clear=True):
            assert _get_cache_retention_min() == 15

    @pytest.mark.parametrize("value", ["-1", "-15"])
    def test_negative_values_return_zero(self, value: str) -> None:
        """Negative values are clamped to zero."""
        with patch.dict(os.environ, {"TAPMAP_CACHE_RETENTION_MIN": value}, clear=True):
            assert _get_cache_retention_min() == 0

    @pytest.mark.parametrize("value", ["abc", "1.5", ""])
    def test_invalid_values_return_config_default(self, value: str) -> None:
        """Invalid values fall back to config default."""
        with patch.dict(os.environ, {"TAPMAP_CACHE_RETENTION_MIN": value}, clear=True):
            assert _get_cache_retention_min() == 0
