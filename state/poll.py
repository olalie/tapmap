"""High level poll action decisions.

Decide which model operation to execute
based on triggers and keyboard actions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ACTION_GEO_RECHECK = "geo_recheck"
ACTION_CLEAR_CACHE = "clear_cache"
ACTION_CACHE_TERMINAL = "cache_terminal"
ACTION_NORMAL_POLL = "normal_poll"


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
    RECHECK_TRIGGERS = {"menu_recheck_geoip", "btn_check_databases"}

    if trigger in RECHECK_TRIGGERS:
        return PollDecision(action=ACTION_GEO_RECHECK)

    if trigger == "menu_clear_cache":
        return PollDecision(action=ACTION_CLEAR_CACHE)

    if trigger == "menu_cache_terminal":
        return PollDecision(action=ACTION_CACHE_TERMINAL)

    if trigger == "key_action":
        action = _extract_key_action(key_action)
        if action == "menu_recheck_geoip":
            return PollDecision(action=ACTION_GEO_RECHECK)
        if action == "menu_clear_cache":
            return PollDecision(action=ACTION_CLEAR_CACHE)
        if action == "menu_cache_terminal":
            return PollDecision(action=ACTION_CACHE_TERMINAL)

    return PollDecision(action=ACTION_NORMAL_POLL)