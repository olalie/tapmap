"""Own the accumulated per-service connection cache for the TapMap state layer.

Merge Model.snapshot() map candidates into a per-service cache, prune
entries past the configured retention window, and backfill deferred
AppInfo verification results into retained entries.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .normalization import safe_int, safe_str

UNKNOWN_APP_KEY = "__unknown_application__"


class ConnectionState:
    """Own and mutate the accumulated per-service connection cache."""

    def __init__(self, cache_retention_min: int = 0) -> None:
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

    @staticmethod
    def _service_key(ip: str, port: int) -> str:
        return f"{ip}|{port}"

    @staticmethod
    def _now_text() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def merge(self, map_candidates: list[dict[str, Any]]) -> dict[str, Any]:
        """Merge map candidates into the cache, prune stale entries, and return the cache."""
        now = datetime.now().timestamp()
        cache = self._cache

        for candidate in map_candidates:
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

            key = self._service_key(ip, port)
            entry = cache.get(key)

            if not isinstance(entry, dict):
                entry = self._new_entry(candidate, ip=ip, port=port, proto=proto)
                cache[key] = entry

            entry["last_seen"] = now

            self._merge_missing_attrs(
                entry,
                candidate,
                attrs=(
                    "proto",
                    "lon",
                    "lat",
                    "city",
                    "country",
                    "country_code",
                    "asn",
                    "asn_org",
                ),
            )

            self._merge_application(
                entry, exe=exe, candidate=candidate, process_name=process_name, pid=pid
            )

        self._prune_cache(cache, now)
        return cache

    def pending_exe_paths(self) -> set[str]:
        """Return exe paths in the cache whose deferred AppInfo data is still missing.

        Scans the accumulated cache, not the current snapshot, so retained
        applications whose connection has vanished are still included.
        Excludes the synthetic unknown-application bucket and applications
        already resolved.
        """
        pending: set[str] = set()
        for entry in self._cache.values():
            if not isinstance(entry, dict):
                continue
            applications = entry.get("applications")
            if not isinstance(applications, dict):
                continue
            for app in applications.values():
                if not isinstance(app, dict):
                    continue
                exe = app.get("exe")
                if not isinstance(exe, str) or not exe:
                    continue
                if app.get("app_verification_status") is None:
                    pending.add(exe)
        return pending

    def refresh_resolved_applications(self, resolved: dict[str, dict[str, Any]]) -> None:
        """Backfill newly-completed AppInfo fields into matching application records.

        resolved maps exe path to a plain dict of app_creator,
        app_verification_status, app_signature_state, and
        app_signature_state_details values. Only fills fields still None, so
        calling this every poll tick is safe even when nothing changed.
        Mutates the cache in place.
        """
        if not resolved:
            return
        for entry in self._cache.values():
            if not isinstance(entry, dict):
                continue
            applications = entry.get("applications")
            if not isinstance(applications, dict):
                continue
            for app in applications.values():
                if not isinstance(app, dict):
                    continue
                exe = app.get("exe")
                if not isinstance(exe, str):
                    continue
                update = resolved.get(exe)
                if update is None:
                    continue
                self._merge_missing_attrs(
                    app,
                    update,
                    attrs=(
                        "app_creator",
                        "app_verification_status",
                        "app_signature_state",
                        "app_signature_state_details",
                    ),
                )

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

    def _new_entry(
        self, candidate: dict[str, Any], *, ip: str, port: int, proto: str | None
    ) -> dict[str, Any]:
        return {
            "ip": ip,
            "port": port,
            "proto": proto,
            "lon": candidate.get("lon"),
            "lat": candidate.get("lat"),
            "city": candidate.get("city"),
            "country": candidate.get("country"),
            "country_code": candidate.get("country_code"),
            "asn": candidate.get("asn"),
            "asn_org": candidate.get("asn_org"),
            "f": self._now_text(),
            "l": self._now_text(),
            "m": 0,
            "applications": {},
        }

    @staticmethod
    def _new_application(exe: str | None) -> dict[str, Any]:
        return {
            "app_name": None,
            "app_creator": None,
            "app_verification_status": None,
            "app_signature_state": None,
            "app_signature_state_details": None,
            "exe": exe,
            "processes": [],
            "proc_pids": {},
        }

    @staticmethod
    def _merge_missing_attrs(
        entry: dict[str, Any],
        candidate: dict[str, Any],
        *,
        attrs: tuple[str, ...],
    ) -> None:
        for attr in attrs:
            if entry.get(attr) is None and candidate.get(attr) is not None:
                entry[attr] = candidate.get(attr)

    def _merge_application(
        self,
        entry: dict[str, Any],
        *,
        exe: str | None,
        candidate: dict[str, Any],
        process_name: str,
        pid: int | None,
    ) -> None:
        """Merge one candidate's application metadata into its exe-keyed bucket.

        Candidates with no resolvable exe path share UNKNOWN_APP_KEY, since
        no reliable identity exists to key them individually.
        """
        applications = entry.get("applications")
        apps: dict[str, Any] = applications if isinstance(applications, dict) else {}
        entry["applications"] = apps

        app_key = exe or UNKNOWN_APP_KEY
        app = apps.get(app_key)
        if not isinstance(app, dict):
            app = self._new_application(exe)
            apps[app_key] = app

        self._merge_missing_attrs(
            app,
            candidate,
            attrs=(
                "app_name",
                "app_creator",
                "app_verification_status",
                "app_signature_state",
                "app_signature_state_details",
            ),
        )

        if process_name:
            self._merge_process(app, process_name=process_name, pid=pid)

    def _merge_process(
        self, record: dict[str, Any], *, process_name: str, pid: int | None
    ) -> None:
        processes = record.get("processes")
        proc_list = processes if isinstance(processes, list) else []
        proc_set = {p.strip() for p in proc_list if isinstance(p, str) and p.strip()}
        proc_set.add(process_name)
        record["processes"] = sorted(proc_set, key=str.lower)

        proc_pids = record.get("proc_pids")
        proc_pids_map: dict[str, list[int]] = proc_pids if isinstance(proc_pids, dict) else {}
        record["proc_pids"] = proc_pids_map

        if pid is None:
            return

        existing = proc_pids_map.get(process_name)
        existing_list = existing if isinstance(existing, list) else []
        pid_set = {int(x) for x in existing_list if isinstance(x, int) and x > 0}
        pid_set.add(pid)
        proc_pids_map[process_name] = sorted(pid_set)
