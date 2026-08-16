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
ACTION_NORMAL_POLL = "normal_poll"
ACTION_REBUILD_VIEW = "rebuild_view"
ACTION_ZOOM_CONNECTIONS = "zoom_connections"
ACTION_NONE = "none"

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


def decide_poll_action(*, trigger: Any, key_action: Any, has_polled: bool) -> PollDecision:
    """Decide which high level poll action to execute.

    Only the model timer, and any trigger before the first poll has ever
    completed, observe and merge into the runtime model. Clear actions reset
    the cache without observing. The technical-details toggle rebuilds the
    map view from the existing cache without observing. Every other trigger
    leaves the runtime model untouched.
    """
    if trigger == "menu_clear_cache":
        return PollDecision(action=ACTION_CLEAR_CACHE)

    if trigger == "tick_model" or not has_polled:
        return PollDecision(action=ACTION_NORMAL_POLL)

    if trigger == "key_action":
        action = _extract_key_action(key_action)
        if action == "menu_clear_cache":
            return PollDecision(action=ACTION_CLEAR_CACHE)
        if action == "zoom_connections":
            return PollDecision(action=ACTION_ZOOM_CONNECTIONS)
        if action == "menu_technical_details":
            return PollDecision(action=ACTION_REBUILD_VIEW)
        return PollDecision(action=ACTION_NONE)

    return PollDecision(action=ACTION_NONE)
