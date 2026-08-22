"""Analyze external/public connections and update ConnectionState and Insights."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .connection_state import ConnectionState
from .insights import process_insights


class ConnectionAnalyzer:
    """Update ConnectionState and Insights from a snapshot's cache_items."""

    def __init__(self, connection_state: ConnectionState, insights: dict[str, Any]) -> None:
        self.connection_state = connection_state
        self.insights = insights

    def analyze(self, cache_items: list[dict[str, Any]]) -> dict[str, Any]:
        """Update ConnectionState with mapped PUBLIC connections; return the Insights result."""
        mapped = self._classify_mapped_public(cache_items)
        self.connection_state.merge(mapped)

        now = datetime.now()
        return process_insights(cache_items, self.insights, now)

    @staticmethod
    def _classify_mapped_public(cache_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return cache_items with PUBLIC scope and valid map coordinates."""
        mapped: list[dict[str, Any]] = []
        for item in cache_items:
            if item.get("service_scope") != "PUBLIC":
                continue

            lat = item.get("lat")
            lon = item.get("lon")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                mapped.append(item)

        return mapped
