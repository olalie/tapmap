"""Define notification channels and failure-isolated dispatch."""

from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class NotificationChannel(Protocol):
    """A single notification output."""

    def send(self, event: dict[str, Any]) -> None:
        """Send one Significant Connection event."""


def dispatch_notification(
    event: dict[str, Any],
    channels: list[NotificationChannel],
) -> None:
    """Send an event to all channels without propagating channel failures."""
    for channel in channels:
        try:
            channel.send(event)
        except Exception:
            logger.exception("Notification channel failed: %s", channel)
