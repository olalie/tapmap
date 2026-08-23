"""Own the bounded, chronological history of Significant Connections."""

from __future__ import annotations

from typing import Any

MAX_ENTRIES = 500


class SignificantConnections:
    """Own the Significant Connections event history, oldest first, bounded to MAX_ENTRIES."""

    def __init__(self, items: list[dict[str, Any]]) -> None:
        self._items: list[dict[str, Any]] = list(items[-MAX_ENTRIES:])

    @property
    def items(self) -> list[dict[str, Any]]:
        """Current history, oldest first."""
        return self._items

    def add(self, event: dict[str, Any]) -> None:
        """Append event as the newest entry, then enforce the retention limit."""
        self._items.append(event)
        if len(self._items) > MAX_ENTRIES:
            del self._items[: len(self._items) - MAX_ENTRIES]
