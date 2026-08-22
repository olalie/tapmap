"""Normalize dictionary values to predictable string and integer types."""

from __future__ import annotations

from typing import Any


def safe_str(value: Any) -> str:
    """Return empty string for None, otherwise str(value)."""
    return "" if value is None else str(value)


def safe_int(value: Any, default: int = -1) -> int:
    """Convert value to int, or return default on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
