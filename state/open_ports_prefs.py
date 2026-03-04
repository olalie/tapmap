"""Open Ports modal preference handling.

Contain pure helpers for storing and updating
user preferences related to the Open Ports view.
"""
from __future__ import annotations

from typing import Any


def set_show_system_pref(*, toggle_value: Any, prefs_data: Any) -> dict[str, Any]:
    """Update open ports preferences with show_system toggle state."""
    prefs = dict(prefs_data) if isinstance(prefs_data, dict) else {}
    prefs["show_system"] = isinstance(toggle_value, list) and "on" in toggle_value
    return prefs
