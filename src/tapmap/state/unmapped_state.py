"""Own the accumulated per-service cache of unmapped PUBLIC services.

Contains no mapped-only GeoIP fields.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from . import service_entries
from .normalization import safe_int, safe_str


class UnmappedState:
    """Own and mutate the accumulated per-service cache of unmapped PUBLIC services."""

    def __init__(self, cache_retention_min: int = 0) -> None:
        """Initialize with an empty cache and the given retention window."""
        self.cache_retention_min = int(cache_retention_min)
        self.logger = logging.getLogger(__name__)
        self._cache: dict[str, Any] = {}

    @property
    def cache(self) -> dict[str, Any]:
        """Current accumulated per-service cache."""
        return self._cache

    def clear(self) -> dict[str, Any]:
        """Reset the accumulated cache and return the new (empty) cache."""
        self._cache = {}
        return self._cache

    def merge(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        """Merge unmapped PUBLIC candidates into the cache, prune stale entries, return cache."""
        now = datetime.now().timestamp()
        cache = self._cache

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue

            ip = safe_str(candidate.get("ip"))
            if not ip:
                continue

            port = safe_int(candidate.get("port"))
            if port <= 0:
                continue

            proto = safe_str(candidate.get("proto")) or None
            process_name = safe_str(candidate.get("process_name"))
            pid = safe_int(candidate.get("pid"))
            exe = safe_str(candidate.get("exe")) or None

            key = service_entries.service_key(ip, port)
            entry = cache.get(key)

            if not isinstance(entry, dict):
                entry = self._new_entry(candidate, ip=ip, port=port, proto=proto)
                cache[key] = entry

            entry["last_seen"] = now

            service_entries.merge_missing_attrs(
                entry,
                candidate,
                attrs=("proto", "service"),
            )

            service_entries.merge_application(
                entry, exe=exe, candidate=candidate, process_name=process_name, pid=pid
            )

        self._prune_cache(cache, now)
        return cache

    def pending_exe_paths(self) -> set[str]:
        """Return exe paths in the cache whose deferred AppInfo data is still missing."""
        return service_entries.pending_exe_paths(self._cache)

    def refresh_resolved_applications(self, resolved: dict[str, dict[str, Any]]) -> None:
        """Backfill newly-completed AppInfo fields into matching application records."""
        service_entries.refresh_resolved_applications(self._cache, resolved)

    def _prune_cache(
        self,
        cache: dict[str, Any],
        now: float,
    ) -> None:
        """Remove cache entries older than the configured retention period."""
        retention_min = self.cache_retention_min

        if retention_min <= 0:
            return

        cutoff = now - (retention_min * 60)

        for key, entry in list(cache.items()):
            if entry["last_seen"] < cutoff:
                del cache[key]

    @staticmethod
    def _new_entry(
        candidate: dict[str, Any], *, ip: str, port: int, proto: str | None
    ) -> dict[str, Any]:
        """Return a new entry dict for one unmapped service."""
        return {
            "ip": ip,
            "port": port,
            "proto": proto,
            "service": candidate.get("service"),
            "applications": {},
        }
