"""Define cache and view building for TapMap.

Merge map candidates into a per-service cache keyed by "ip|port", group cached
entries by rounded coordinates, and build hover summaries and click details.

The cache is JSON-friendly and stable:

- Each service key maps to one entry that accumulates across snapshots.
- Each entry keeps both a flat process list and a per-process PID list.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any


class CacheViewBuilder:
    """Build UI cache and map view data."""

    def __init__(self, coord_precision: int = 3, debug: bool = False) -> None:
        self.coord_precision = int(coord_precision)
        self.debug = bool(debug)
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _safe_str(value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            n = int(value)
        except (TypeError, ValueError):
            return None
        return n if n > 0 else None

    @staticmethod
    def _service_key(ip: str, port: int) -> str:
        return f"{ip}|{port}"

    @staticmethod
    def _fmt_ip_port(ip: str, port: int) -> str:
        ip_text = ip or "?"
        port_text = str(int(port)) if isinstance(port, int) else "-"
        if ":" in ip_text and not ip_text.startswith("["):
            return f"[{ip_text}]:{port_text}"
        return f"{ip_text}:{port_text}"

    @staticmethod
    def _safe_proto(value: Any) -> str:
        p = str(value).strip().lower() if value else "tcp"
        return p if p in {"tcp", "udp"} else "tcp"

    @staticmethod
    def format_list_compact(items: list[Any], max_items: int) -> str:
        """Format items as comma-separated values with optional +N overflow."""
        cleaned: list[str] = []
        for item in items:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                cleaned.append(text)

        if not cleaned:
            return "-"

        if len(cleaned) <= max_items:
            return ", ".join(cleaned)

        shown = ", ".join(cleaned[:max_items])
        return f"{shown} +{len(cleaned) - max_items}"

    def merge_map_candidates(
        self,
        ui_cache: dict[str, Any],
        map_candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Merge map candidates into a per-service cache.

        Cache key format:
            "ip|port"

        Stored entry format:
            {
                "ip": str,
                "port": int,
                "proto": str | None,
                "lon": float | None,
                "lat": float | None,
                "city": str | None,
                "country": str | None,
                "asn": Any,
                "asn_org": str | None,
                "first_seen": "YYYY-MM-DD HH:MM:SS",
                "processes": list[str],
                "proc_pids": dict[str, list[int]],
            }
        """
        cache = dict(ui_cache) if isinstance(ui_cache, dict) else {}

        for candidate in map_candidates:
            if not isinstance(candidate, dict):
                continue

            ip = self._safe_str(candidate.get("ip"))
            if not ip:
                continue

            port = self._safe_int(candidate.get("port"))
            if port is None:
                continue

            proto = self._safe_str(candidate.get("proto")) or None
            process_name = self._safe_str(candidate.get("process_name")) or "Unknown"
            pid = self._safe_int(candidate.get("pid"))

            key = self._service_key(ip, port)

            entry = cache.get(key)
            if not isinstance(entry, dict):
                entry = {
                    "ip": ip,
                    "port": port,
                    "proto": proto,
                    "lon": candidate.get("lon"),
                    "lat": candidate.get("lat"),
                    "city": candidate.get("city"),
                    "country": candidate.get("country"),
                    "asn": candidate.get("asn"),
                    "asn_org": candidate.get("asn_org"),
                    "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "processes": [],
                    "proc_pids": {},
                }
                cache[key] = entry

            procs = entry.get("processes")
            procs_set = set(procs) if isinstance(procs, list) else set()
            procs_set.add(process_name)
            entry["processes"] = sorted({p for p in procs_set if isinstance(p, str) and p.strip()})

            proc_pids = entry.get("proc_pids")
            proc_pids_map: dict[str, list[int]] = proc_pids if isinstance(proc_pids, dict) else {}
            entry["proc_pids"] = proc_pids_map

            if pid is not None:
                current = proc_pids_map.get(process_name)
                current_list = current if isinstance(current, list) else []
                current_list.append(pid)
                proc_pids_map[process_name] = sorted(set(current_list))

            for attr in ("proto", "lon", "lat", "city", "country", "asn", "asn_org"):
                if entry.get(attr) is None and candidate.get(attr) is not None:
                    entry[attr] = candidate.get(attr)

        return cache

    def build_view_from_cache(self, ui_cache: dict[str, Any]) -> dict[str, Any]:
        """Group cached entries by rounded coordinates and build map view data."""
        cache = ui_cache if isinstance(ui_cache, dict) else {}

        groups: dict[tuple[float, float], list[dict[str, Any]]] = defaultdict(list)
        for entry in cache.values():
            if not isinstance(entry, dict):
                continue

            lon = entry.get("lon")
            lat = entry.get("lat")
            if lon is None or lat is None:
                continue

            try:
                key = (
                    round(float(lon), self.coord_precision),
                    round(float(lat), self.coord_precision),
                )
            except (TypeError, ValueError):
                continue

            groups[key].append(entry)

        points: list[tuple[float, float]] = []
        summaries: dict[str, str] = {}
        details: dict[str, str] = {}

        for idx, coord in enumerate(sorted(groups)):
            entries = groups[coord]
            lon, lat = coord
            points.append((lon, lat))

            place = self._pick_place(entries)
            service_count = len(entries)

            line1 = f"{place} ({service_count} services)" if service_count > 1 else place
            line2, unique_orgs = self._pick_network_line(entries)

            unique_ports = sorted(
                {int(e.get("port")) for e in entries if isinstance(e.get("port"), int)}
            )
            unique_procs = self._unique_processes(entries)

            ports_txt = self.format_list_compact([str(p) for p in unique_ports], max_items=3)
            procs_txt = self.format_list_compact(unique_procs, max_items=2)
            line3 = f"Ports: {ports_txt} | Procs: {procs_txt}"

            key_str = str(idx)
            summaries[key_str] = f"{line1}<br>{line2}<br>{line3}"

            unique_ips = sorted({e.get("ip") for e in entries if e.get("ip")})
            counts_line = (
                f"Services: {service_count} | "
                f"Networks: {len(unique_orgs)} | "
                f"IPs: {len(unique_ips)} | "
                f"Ports: {len(unique_ports)} | "
                f"Procs: {len(unique_procs)}"
            )

            org_blocks = self._build_org_blocks(entries)

            details[key_str] = (
                f"Location: {place}\n{counts_line}\n\n" + "\n\n".join(org_blocks)
            )

        return {
            "points": points,
            "summaries": summaries,
            "details": details,
        }

    def debug_coords(self, ui_cache: dict[str, Any], *, top_n: int = 10) -> None:
        """Log coordinate collision statistics."""
        if not self.debug:
            return

        cache = ui_cache if isinstance(ui_cache, dict) else {}

        coords: list[tuple[float, float]] = []
        for entry in cache.values():
            if not isinstance(entry, dict):
                continue

            lon = entry.get("lon")
            lat = entry.get("lat")
            if lon is None or lat is None:
                continue

            try:
                coords.append(
                    (
                        round(float(lon), self.coord_precision),
                        round(float(lat), self.coord_precision),
                    )
                )
            except (TypeError, ValueError):
                continue

        total = len(coords)
        unique = len(set(coords))
        self.logger.debug("Coords: total=%s unique=%s", total, unique)

        counts = Counter(coords)
        top = [(k, n) for k, n in counts.most_common(top_n) if n > 1]
        if not top:
            return

        self.logger.debug("Top coord duplicates:")
        for (lon, lat), n in top:
            self.logger.debug("  (%s, %s) x%s", lon, lat, n)

    def _pick_place(self, entries: list[dict[str, Any]]) -> str:
        cities = [e.get("city") for e in entries if e.get("city")]
        countries = [e.get("country") for e in entries if e.get("country")]

        city = Counter(cities).most_common(1)[0][0] if cities else None
        country = Counter(countries).most_common(1)[0][0] if countries else None

        if city and country:
            return f"{city}, {country}"
        if country:
            return str(country)
        return "Unknown place name"

    def _pick_network_line(self, entries: list[dict[str, Any]]) -> tuple[str, list[str]]:
        unique_orgs = sorted({e.get("asn_org") for e in entries if e.get("asn_org")})
        if len(unique_orgs) == 1:
            return unique_orgs[0], unique_orgs
        if not unique_orgs:
            return "Unknown network", unique_orgs
        return f"Multiple networks ({len(unique_orgs)})", unique_orgs

    def _unique_processes(self, entries: list[dict[str, Any]]) -> list[str]:
        out: set[str] = set()
        for e in entries:
            procs = e.get("processes")
            if not isinstance(procs, list):
                continue
            for p in procs:
                if isinstance(p, str) and p.strip():
                    out.add(p.strip())
        return sorted(out, key=str.lower)

    def _build_org_blocks(self, entries: list[dict[str, Any]]) -> list[str]:
        by_org: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for e in entries:
            org = e.get("asn_org")
            org_txt = org.strip() if isinstance(org, str) and org.strip() else "Unknown network"
            by_org[org_txt].append(e)

        org_blocks: list[str] = []
        for org in sorted(by_org.keys(), key=str.lower):
            org_entries = sorted(by_org[org], key=self._service_sort_key)

            lines: list[str] = []
            lines.append(org)

            for e in org_entries:
                ip = self._safe_str(e.get("ip")) or "?"
                port = e.get("port")
                port_i = int(port) if isinstance(port, int) else -1
                port_txt = port_i if port_i > 0 else -1

                proto = self._safe_proto(e.get("proto"))
                addr = self._fmt_ip_port(ip, port_i if port_i > 0 else 0)

                lines.append(f"  {addr} ({proto})")
                lines.append(f"    Procs: {self._format_procs_with_pids(e)}")
                lines.append("")

            org_blocks.append("\n".join(lines))

        return org_blocks

    @staticmethod
    def _service_sort_key(x: dict[str, Any]) -> tuple[str, int]:
        ip = x.get("ip")
        ip_txt = ip if isinstance(ip, str) else ""
        port = x.get("port")
        port_i = port if isinstance(port, int) else 0
        return (ip_txt, port_i)

    def _format_procs_with_pids(self, entry: dict[str, Any]) -> str:
        procs_raw = entry.get("processes")
        procs = (
            sorted({p.strip() for p in procs_raw if isinstance(p, str) and p.strip()}, key=str.lower)
            if isinstance(procs_raw, list)
            else []
        )

        proc_pids_raw = entry.get("proc_pids")
        proc_pids: dict[str, list[int]] = proc_pids_raw if isinstance(proc_pids_raw, dict) else {}

        parts: list[str] = []
        for p in procs:
            pids_raw = proc_pids.get(p)
            pid_list = sorted({int(x) for x in pids_raw if isinstance(x, int) and x > 0}) if isinstance(pids_raw, list) else []
            if pid_list:
                parts.append(f"{p} (pid {', '.join(str(x) for x in pid_list)})")
            else:
                parts.append(p)

        return ", ".join(parts) if parts else "-"