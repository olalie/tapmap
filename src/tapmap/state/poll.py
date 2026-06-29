"""High level poll action decisions.

Decide which model operation to execute
based on triggers and keyboard actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ACTION_GEO_RECHECK = "geo_recheck"
ACTION_GEO_INSTALL_MAXMIND = "geo_install_maxmind"
ACTION_GEO_INSTALL_DBIP = "geo_install_dbip"
ACTION_GEO_UPDATE = "geo_update"
ACTION_CLEAR_CACHE = "clear_cache"
ACTION_CACHE_TERMINAL = "cache_terminal"
ACTION_NORMAL_POLL = "normal_poll"
ACTION_ZOOM_CONNECTIONS = "zoom_connections"

@dataclass(frozen=True)
class PollDecision:
    """Describe which poll action to execute."""

    action: str


def _extract_key_action(key_action: Any) -> str | None:
    """Extract action string from key_action store payload."""
    if not isinstance(key_action, dict):
        return None
    action = key_action.get("action")
    return action if isinstance(action, str) and action else None


def decide_poll_action(*, trigger: Any, key_action: Any) -> PollDecision:
    """Decide which high level poll action to execute.

    Handles direct menu clicks and keyboard actions. Otherwise returns normal_poll.
    """
    if trigger == "menu_clear_cache":
        return PollDecision(action=ACTION_CLEAR_CACHE)

    if trigger == "menu_cache_terminal":
        return PollDecision(action=ACTION_CACHE_TERMINAL)

    if trigger == "key_action":
        action = _extract_key_action(key_action)
        if action == "menu_clear_cache":
            return PollDecision(action=ACTION_CLEAR_CACHE)
        if action == "menu_cache_terminal":
            return PollDecision(action=ACTION_CACHE_TERMINAL)
        if action == "zoom_connections":
            return PollDecision(action=ACTION_ZOOM_CONNECTIONS)

    return PollDecision(action=ACTION_NORMAL_POLL)
