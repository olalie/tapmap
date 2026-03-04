"""Keyboard action parsing and normalization.

Translate raw key input into high level action strings
used by the application state layer.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

KEY_MAP = {
    "__u__": "menu_unmapped",
    "__l__": "menu_lan_local",
    "__o__": "menu_open_ports",
    "__t__": "menu_cache_terminal",
    "__c__": "menu_clear_cache",
    "__r__": "menu_recheck_geoip",
    "__h__": "menu_help",
    "__a__": "menu_about",
    "__esc__": "escape",
}

def build_key_action(value: str) -> dict[str, Any] | None:
    """Build key action payload from capture value."""
    if not value:
        return None

    token = value.split("|", 1)[0]
    action = KEY_MAP.get(token)
    if not action:
        return None

    return {"action": action, "t": datetime.now().isoformat()}
