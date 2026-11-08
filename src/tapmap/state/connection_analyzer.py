"""Analyze connections and route them to state: mapped, unmapped, insights, significant.

Mapped PUBLIC connections update ConnectionState and feed Insights. PUBLIC
connections without usable GeoIP update UnmappedState and remain eligible
for Significant Connections, but do not contribute to Insights.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from ..notifications.channel import NotificationChannel, dispatch_notification
from .connection_state import ConnectionState
from .insights import distinct_active_days, process_insights
from .insights_state import InsightsState
from .notification_policy import is_learning_period_over, record_learning_completion
from .significance import SignificanceHistory, get_significant
from .significant_connections import SignificantConnections
from .unmapped_state import UnmappedState

logger = logging.getLogger(__name__)


class ConnectionAnalyzer:
    """Process a snapshot's connections and update derived state and notifications."""

    def __init__(
        self,
        connection_state: ConnectionState,
        unmapped_state: UnmappedState,
        insights_state: InsightsState,
        significant_connections: SignificantConnections,
        significance_history: SignificanceHistory,
        *,
        notification_channels: list[NotificationChannel] | None = None,
        notification_learning_days: int = 7,
    ) -> None:
        """Store references to the collaborating state and history objects."""
        self.connection_state = connection_state
        self.unmapped_state = unmapped_state
        self.insights_state = insights_state
        self.significant_connections = significant_connections
        self.significance_history = significance_history
        self.notification_channels = (
            notification_channels if notification_channels is not None else []
        )
        self.notification_learning_days = notification_learning_days
        self._is_learning_suppression_logged = False

    def analyze(self, connections: list[dict[str, Any]]) -> dict[str, Any]:
        """Update ConnectionState, UnmappedState, Significant Connections, and Insights.

        Insights is derived only from mapped PUBLIC connections. Notification
        eligibility is evaluated once, before this poll updates Insights; the
        learning period completion is recorded in insights_state. Returns the
        Insights result ({top}).
        """
        now = datetime.now()
        if record_learning_completion(
            self.insights_state, self.notification_learning_days, now.date().toordinal()
        ):
            logger.info(
                "Notification learning period completed after %d active Insights days; "
                "notifications are enabled.",
                self.notification_learning_days,
            )
        is_notification_allowed = is_learning_period_over(
            self.insights_state, self.notification_learning_days
        )
        has_suppressed_event = False
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
                if is_notification_allowed:
                    dispatch_notification(significant_connection, self.notification_channels)
                else:
                    has_suppressed_event = True

        if has_suppressed_event and not self._is_learning_suppression_logged:
            self._is_learning_suppression_logged = True
            logger.info(
                "Significant Connections are recorded; notifications start after %d active "
                "Insights days (%d so far).",
                self.notification_learning_days,
                distinct_active_days(self.insights_state.insights),
            )

        self.connection_state.merge(mapped)
        self.unmapped_state.merge(unmapped)

        return process_insights(mapped, self.insights_state.insights, now)
