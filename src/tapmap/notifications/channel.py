"""Channel abstraction and dispatch for notification delivery.

Each channel is an independent output: one channel's failure must never
prevent another channel from being attempted, and must never propagate to the
caller (the connection-analysis poll loop).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class NotificationChannel(Protocol):
    """A single notification output."""

    def send(self, event: dict[str, Any]) -> None:
        """Deliver one Significant Connection event through this channel."""


def dispatch_notification(
    event: dict[str, Any],
    channels: list[NotificationChannel],
) -> None:
    """Send event to every channel independently; one failure never stops another."""
    for channel in channels:
        try:
            channel.send(event)
        except Exception:
            logger.exception("Notification channel failed: %s", channel)
