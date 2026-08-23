"""Analyze connections and update ConnectionState, Insights, and Significant Connections."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .connection_state import ConnectionState
from .insights import process_insights
from .significance import SignificanceHistory, get_significant
from .significant_connections import SignificantConnections


class ConnectionAnalyzer:
    """Process a snapshot's cache_items: connection state, Significant Connections, and Insights."""

    def __init__(
        self,
        connection_state: ConnectionState,
        insights: dict[str, Any],
        significant_connections: SignificantConnections,
        significance_history: SignificanceHistory,
    ) -> None:
        self.connection_state = connection_state
        self.insights = insights
        self.significant_connections = significant_connections
        self.significance_history = significance_history

    def analyze(self, cache_items: list[dict[str, Any]]) -> dict[str, Any]:
        """Update ConnectionState, Significant Connections, and Insights from cache_items.

        Returns the Insights result ({new, top}).
        """
        now = datetime.now()
        mapped: list[dict[str, Any]] = []

        for item in cache_items:
            if item.get("service_scope") != "PUBLIC":
                continue

            lat = item.get("lat")
            lon = item.get("lon")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                mapped.append(item)

            significant_connection = get_significant(item, self.significance_history, now)
            if significant_connection is not None:
                self.significant_connections.add(significant_connection)

        self.connection_state.merge(mapped)

        return process_insights(cache_items, self.insights, now)
