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

    # Safe conversions
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

    # Keys and formats
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
    def _now_text() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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

    # Cache merge
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
                entry = self._new_entry(candidate, ip=ip, port=port, proto=proto)
                cache[key] = entry

            self._merge_process(entry, process_name=process_name, pid=pid)
            self._merge_missing_attrs(
                entry,
                candidate,
                attrs=("proto", "lon", "lat", "city", "country", "asn", "asn_org"),
            )

        return cache

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
            "asn": candidate.get("asn"),
            "asn_org": candidate.get("asn_org"),
            "first_seen": self._now_text(),
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

    def _merge_process(self, entry: dict[str, Any], *, process_name: str, pid: int | None) -> None:
        processes = entry.get("processes")
        proc_list = processes if isinstance(processes, list) else []
        proc_set = {p.strip() for p in proc_list if isinstance(p, str) and p.strip()}
        proc_set.add(process_name)
        entry["processes"] = sorted(proc_set, key=str.lower)

        proc_pids = entry.get("proc_pids")
        proc_pids_map: dict[str, list[int]] = proc_pids if isinstance(proc_pids, dict) else {}
        entry["proc_pids"] = proc_pids_map

        if pid is None:
            return

        existing = proc_pids_map.get(process_name)
        existing_list = existing if isinstance(existing, list) else []
        pid_set = {int(x) for x in existing_list if isinstance(x, int) and x > 0}
        pid_set.add(pid)
        proc_pids_map[process_name] = sorted(pid_set)

    # View building
    def build_view_from_cache(self, ui_cache: dict[str, Any]) -> dict[str, Any]:
        """Group cached entries by rounded coordinates and build map view data."""
        cache = ui_cache if isinstance(ui_cache, dict) else {}
        groups = self._group_by_coord(cache)

        points: list[tuple[float, float]] = []
        summaries: dict[str, str] = {}
        details: dict[str, str] = {}

        for idx, coord in enumerate(sorted(groups)):
            entries = groups[coord]
            lon, lat = coord
            points.append((lon, lat))

            place = self._pick_place(entries)
            orgs = self._unique_network_orgs(entries)
            service_count = len(entries)

            hover = self._build_hover_summary(place, service_count, entries, orgs)
            key_str = str(idx)
            summaries[key_str] = hover

            details[key_str] = self._build_click_details(place, entries, orgs)

        return {"points": points, "summaries": summaries, "details": details}

    def _group_by_coord(self, cache: dict[str, Any]) -> dict[tuple[float, float], list[dict[str, Any]]]:
        groups: dict[tuple[float, float], list[dict[str, Any]]] = defaultdict(list)

        for raw in cache.values():
            if not isinstance(raw, dict):
                continue

            lon = raw.get("lon")
            lat = raw.get("lat")
            if lon is None or lat is None:
                continue

            try:
                key = (round(float(lon), self.coord_precision), round(float(lat), self.coord_precision))
            except (TypeError, ValueError):
                continue

            groups[key].append(raw)

        return groups

    def _build_hover_summary(
        self,
        place: str,
        service_count: int,
        entries: list[dict[str, Any]],
        unique_orgs: list[str],
    ) -> str:
        line1 = f"{place} ({service_count} services)" if service_count > 1 else place

        if len(unique_orgs) == 1:
            line2 = unique_orgs[0]
        elif not unique_orgs:
            line2 = "Unknown network"
        else:
            line2 = f"Multiple networks ({len(unique_orgs)})"

        unique_ports = self._unique_ports(entries)
        unique_procs = self._unique_processes(entries)

        ports_txt = self.format_list_compact([str(p) for p in unique_ports], max_items=3)
        procs_txt = self.format_list_compact(unique_procs, max_items=2)
        line3 = f"Ports: {ports_txt} | Procs: {procs_txt}"

        return f"{line1}<br>{line2}<br>{line3}"

    def _build_click_details(self, place: str, entries: list[dict[str, Any]], unique_orgs: list[str]) -> str:
        unique_ips = self._unique_ips(entries)
        unique_ports = self._unique_ports(entries)
        unique_procs = self._unique_processes(entries)

        counts_line = (
            f"Services: {len(entries)} | "
            f"Networks: {len(unique_orgs)} | "
            f"IPs: {len(unique_ips)} | "
            f"Ports: {len(unique_ports)} | "
            f"Procs: {len(unique_procs)}"
        )

        org_blocks = self._build_org_blocks(entries)
        return f"Location: {place}\n{counts_line}\n\n" + "\n\n".join(org_blocks)

    # Aggregation helpers
    @staticmethod
    def _pick_place(entries: list[dict[str, Any]]) -> str:
        cities = [e.get("city") for e in entries if e.get("city")]
        countries = [e.get("country") for e in entries if e.get("country")]

        city = Counter(cities).most_common(1)[0][0] if cities else None
        country = Counter(countries).most_common(1)[0][0] if countries else None

        if city and country:
            return f"{city}, {country}"
        if country:
            return str(country)
        return "Unknown place name"

    @staticmethod
    def _unique_network_orgs(entries: list[dict[str, Any]]) -> list[str]:
        orgs = {e.get("asn_org") for e in entries if isinstance(e.get("asn_org"), str) and e.get("asn_org")}
        return sorted({o.strip() for o in orgs if isinstance(o, str) and o.strip()}, key=str.lower)

    @staticmethod
    def _unique_ports(entries: list[dict[str, Any]]) -> list[int]:
        ports: set[int] = set()
        for e in entries:
            p = e.get("port")
            if isinstance(p, int) and p > 0:
                ports.add(int(p))
        return sorted(ports)

    @staticmethod
    def _unique_ips(entries: list[dict[str, Any]]) -> list[str]:
        ips = {e.get("ip") for e in entries if isinstance(e.get("ip"), str) and e.get("ip")}
        return sorted({ip.strip() for ip in ips if isinstance(ip, str) and ip.strip()}, key=str.lower)

    @staticmethod
    def _unique_processes(entries: list[dict[str, Any]]) -> list[str]:
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
            org_val = e.get("asn_org")
            org = org_val.strip() if isinstance(org_val, str) and org_val.strip() else "Unknown network"
            by_org[org].append(e)

        blocks: list[str] = []
        for org in sorted(by_org.keys(), key=str.lower):
            org_entries = sorted(by_org[org], key=self._service_sort_key)
            blocks.append(self._format_org_block(org, org_entries))

        return blocks

    @staticmethod
    def _service_sort_key(e: dict[str, Any]) -> tuple[str, int]:
        ip = e.get("ip")
        ip_txt = ip if isinstance(ip, str) else ""
        port = e.get("port")
        port_i = port if isinstance(port, int) else 0
        return (ip_txt, port_i)

    def _format_org_block(self, org: str, org_entries: list[dict[str, Any]]) -> str:
        lines: list[str] = [org]

        for e in org_entries:
            ip = self._safe_str(e.get("ip")) or "?"
            port = e.get("port")
            port_i = int(port) if isinstance(port, int) and port > 0 else 0

            proto = self._safe_proto(e.get("proto"))
            addr = self._fmt_ip_port(ip, port_i)
            procs_txt = self._format_procs_with_pids(e)

            lines.append(f"  {addr} ({proto})")
            lines.append(f"    Procs: {procs_txt}")
            lines.append("")

        return "\n".join(lines)

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
            pids = (
                sorted({int(x) for x in pids_raw if isinstance(x, int) and x > 0})
                if isinstance(pids_raw, list)
                else []
            )
            if pids:
                parts.append(f"{p} (pid {', '.join(str(x) for x in pids)})")
            else:
                parts.append(p)

        return ", ".join(parts) if parts else "-"

    # Debug helpers
    def debug_coords(self, ui_cache: dict[str, Any], *, top_n: int = 10) -> None:
        """Log coordinate collision statistics."""
        if not self.debug:
            return

        cache = ui_cache if isinstance(ui_cache, dict) else {}
        coords: list[tuple[float, float]] = []

        for raw in cache.values():
            if not isinstance(raw, dict):
                continue

            lon = raw.get("lon")
            lat = raw.get("lat")
            if lon is None or lat is None:
                continue

            try:
                coords.append((round(float(lon), self.coord_precision), round(float(lat), self.coord_precision)))
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