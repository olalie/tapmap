"""Analyze connections and route them to state: mapped, unmapped, insights, significant.

Mapped PUBLIC connections update ConnectionState and feed Insights. PUBLIC
connections without usable GeoIP update UnmappedState and remain eligible
for Significant Connections, but do not contribute to Insights.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..notifications.channel import NotificationChannel, dispatch_notification
from .connection_state import ConnectionState
from .insights import process_insights
from .notification_policy import is_learning_period_over
from .significance import SignificanceHistory, get_significant
from .significant_connections import SignificantConnections
from .unmapped_state import UnmappedState


class ConnectionAnalyzer:
    """Process a snapshot's connections and update derived state and notifications."""

    def __init__(
        self,
        connection_state: ConnectionState,
        unmapped_state: UnmappedState,
        insights: dict[str, Any],
        significant_connections: SignificantConnections,
        significance_history: SignificanceHistory,
        *,
        notification_channels: list[NotificationChannel] | None = None,
        notification_learning_days: int = 7,
    ) -> None:
        """Store references to the collaborating state and history objects."""
        self.connection_state = connection_state
        self.unmapped_state = unmapped_state
        self.insights = insights
        self.significant_connections = significant_connections
        self.significance_history = significance_history
        self.notification_channels = (
            notification_channels if notification_channels is not None else []
        )
        self.notification_learning_days = notification_learning_days

    def analyze(self, connections: list[dict[str, Any]]) -> dict[str, Any]:
        """Update ConnectionState, UnmappedState, Significant Connections, and Insights.

        Insights is derived only from mapped PUBLIC connections. Returns the
        Insights result ({new, top}).
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
                if is_learning_period_over(self.insights, self.notification_learning_days):
                    dispatch_notification(significant_connection, self.notification_channels)

        self.connection_state.merge(mapped)
        self.unmapped_state.merge(unmapped)

        return process_insights(mapped, self.insights, now)
