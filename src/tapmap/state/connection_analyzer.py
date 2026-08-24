"""Analyze connections and route them to state: mapped, unmapped, insights, significant.

Mapped PUBLIC connections update ConnectionState; PUBLIC connections without
usable GeoIP update UnmappedState.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .connection_state import ConnectionState
from .insights import process_insights
from .significance import SignificanceHistory, get_significant
from .significant_connections import SignificantConnections
from .unmapped_state import UnmappedState


class ConnectionAnalyzer:
    """Process a snapshot's connections: connection, unmapped, insights, and significant state."""

    def __init__(
        self,
        connection_state: ConnectionState,
        unmapped_state: UnmappedState,
        insights: dict[str, Any],
        significant_connections: SignificantConnections,
        significance_history: SignificanceHistory,
    ) -> None:
        """Store references to the collaborating state and history objects."""
        self.connection_state = connection_state
        self.unmapped_state = unmapped_state
        self.insights = insights
        self.significant_connections = significant_connections
        self.significance_history = significance_history

    def analyze(self, connections: list[dict[str, Any]]) -> dict[str, Any]:
        """Update ConnectionState, UnmappedState, Significant Connections, and Insights.

        Returns the Insights result ({new, top}).
        """
        now = datetime.now()
        mapped: list[dict[str, Any]] = []
        unmapped: list[dict[str, Any]] = []

        for item in connections:
            if item.get("service_scope") != "PUBLIC":
                continue

            lat = item.get("lat")
            lon = item.get("lon")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                mapped.append(item)
            else:
                unmapped.append(item)

            significant_connection = get_significant(item, self.significance_history, now)
            if significant_connection is not None:
                self.significant_connections.add(significant_connection)

        self.connection_state.merge(mapped)
        self.unmapped_state.merge(unmapped)

        return process_insights(connections, self.insights, now)
