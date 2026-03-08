"""Status line rendering logic.

Build human readable status text from
snapshot, cache state, and flash messages.
"""

from __future__ import annotations

from typing import Any

from state.status_cache import StatusCache


def render_status_text(
    *,
    snapshot: Any,
    status_cache_data: Any,
    status_flash: Any,
    myloc_label: str,
    to_int: Any,
) -> str:
    """Render status bar text."""
    if isinstance(status_flash, dict):
        message = status_flash.get("message")
        if isinstance(message, str) and message:
            return message

    status_cache = StatusCache.from_store(status_cache_data)
    cache_chain = status_cache.format_chain()

    live_tcp_total = 0
    live_tcp_established = 0
    live_tcp_listen = 0
    live_udp_remote = 0
    live_udp_bound = 0
    updated = "--:--:--"
    status = "WAIT"
    note = ""

    if isinstance(snapshot, dict):
        if snapshot.get("error"):
            status = "ERROR"
            note = " (see terminal)"
        else:
            stats = snapshot.get("stats")
            if isinstance(stats, dict):
                online = bool(stats.get("online", True))
                status = "OK" if online else "OFFLINE"
                live_tcp_total = to_int(stats.get("live_tcp_total"))
                live_tcp_established = to_int(stats.get("live_tcp_established"))
                live_tcp_listen = to_int(stats.get("live_tcp_listen"))
                live_udp_remote = to_int(stats.get("live_udp_remote"))
                live_udp_bound = to_int(stats.get("live_udp_bound"))
                updated = stats.get("updated") or updated

    return (
        f"STATUS: {status}{note} | "
        f"LIVE: TCP {live_tcp_total} EST {live_tcp_established} "
        f"LST {live_tcp_listen} UDP R {live_udp_remote} "
        f"B {live_udp_bound} | "
        f"CACHE: {cache_chain} | "
        f"UPDATED: {updated} | "
        f"MYLOC: {myloc_label}"
    )
