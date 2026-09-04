"""Own the bounded, chronological history of Significant Connections."""

from __future__ import annotations

from typing import Any

from .service_entries import merge_missing_attrs

MAX_ENTRIES = 500

_DEFERRED_VERIFICATION_ATTRS = (
    "app_creator",
    "app_verification_status",
    "app_signature_state",
    "app_signature_state_details",
)

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

    def find_by_identity(
        self, *, timestamp: Any, pid: Any, ip: Any, port: Any, proto: Any
    ) -> dict[str, Any] | None:
        """Return the persisted event matching these five identity fields, or None if not found."""
        for event in self._items:
            if (
                event.get("timestamp") == timestamp
                and event.get("pid") == pid
                and event.get("ip") == ip
                and event.get("port") == port
                and event.get("proto") == proto
            ):
                return event
        return None

    def pending_exe_paths(self) -> set[str]:
        """Return exe paths of persisted events whose deferred verification is still missing."""
        pending: set[str] = set()
        for event in self._items:
            exe = event.get("exe")
            if not isinstance(exe, str) or not exe:
                continue
            if event.get("app_verification_status") is None:
                pending.add(exe)
        return pending

    def refresh_resolved_applications(self, resolved: dict[str, dict[str, Any]]) -> None:
        """Backfill newly-completed AppInfo fields into persisted events still pending for that exe.

        resolved maps exe path to a plain dict of app_creator,
        app_verification_status, app_signature_state, and
        app_signature_state_details values, matching ConnectionState's and
        UnmappedState's refresh_resolved_applications(). Only fills fields
        still None on a matching event - timestamp, reasons, and every
        connection/geographic field are left untouched. A later, independent
        significant event (e.g. a fresh verification_failed detection) is
        unaffected: this only ever fills currently-None fields on already
        persisted events, never adds, merges, or removes events.
        """
        if not resolved:
            return
        for event in self._items:
            exe = event.get("exe")
            if not isinstance(exe, str):
                continue
            update = resolved.get(exe)
            if update is None:
                continue
            merge_missing_attrs(event, update, attrs=_DEFERRED_VERIFICATION_ATTRS)
