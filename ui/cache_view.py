"""Define cache and view building for TapMap.

Merge map candidates into a per-service cache keyed by "ip|port", group cached
entries by rounded coordinates, and build hover summaries and click details.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any


class CacheViewBuilder:
    """Build UI cache and map view data."""

    def __init__(self, coord_precision: int = 3, debug: bool = False):
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
                "lon": float | None,
                "lat": float | None,
                "city": str | None,
                "country": str | None,
                "asn": Any,
                "asn_org": str | None,
                "first_seen": "YYYY-MM-DD HH:MM:SS",
                "processes": list[str],
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

            process_name = self._safe_str(candidate.get("process_name")) or "Unknown"
            key = self._service_key(ip, port)

            entry = cache.get(key)
            if not isinstance(entry, dict):
                entry = {
                    "ip": ip,
                    "port": port,
                    "lon": candidate.get("lon"),
                    "lat": candidate.get("lat"),
                    "city": candidate.get("city"),
                    "country": candidate.get("country"),
                    "asn": candidate.get("asn"),
                    "asn_org": candidate.get("asn_org"),
                    "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "processes": [],
                }
                cache[key] = entry

            procs = entry.get("processes")
            procs_set = set(procs) if isinstance(procs, list) else set()
            procs_set.add(process_name)
            entry["processes"] = sorted({p for p in procs_set if isinstance(p, str) and p.strip()})

            for attr in ("lon", "lat", "city", "country", "asn", "asn_org"):
                if entry.get(attr) is None and candidate.get(attr) is not None:
                    entry[attr] = candidate.get(attr)

        return cache

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

    def build_view_from_cache(self, ui_cache: dict[str, Any]) -> dict[str, Any]:
        """Group cached entries by rounded coordinates and build map view data."""
        cache = ui_cache if isinstance(ui_cache, dict) else {}

        groups: dict[tuple[float, float], list[dict[str, Any]]] = defaultdict(list)
        for entry in cache.values():
            lon = entry.get("lon")
            lat = entry.get("lat")
            if lon is None or lat is None:
                continue

            key = (
                round(float(lon), self.coord_precision),
                round(float(lat), self.coord_precision),
            )
            groups[key].append(entry)

        points: list[tuple[float, float]] = []
        summaries: dict[str, str] = {}
        details: dict[str, str] = {}

        for idx, coord in enumerate(sorted(groups)):
            entries = groups[coord]
            lon, lat = coord
            points.append((lon, lat))

            cities = [e.get("city") for e in entries if e.get("city")]
            countries = [e.get("country") for e in entries if e.get("country")]

            city = Counter(cities).most_common(1)[0][0] if cities else None
            country = Counter(countries).most_common(1)[0][0] if countries else None

            service_count = len(entries)

            if city and country:
                place = f"{city}, {country}"
            elif country:
                place = country
            else:
                place = "Unknown place name"

            line1 = f"{place} ({service_count} services)" if service_count > 1 else place

            unique_orgs = sorted({e.get("asn_org") for e in entries if e.get("asn_org")})
            if len(unique_orgs) == 1:
                line2 = unique_orgs[0]
            elif not unique_orgs:
                line2 = "Unknown network"
            else:
                line2 = f"Multiple networks ({len(unique_orgs)})"

            unique_ports = sorted(
                {int(e.get("port")) for e in entries if isinstance(e.get("port"), int)}
            )
            unique_procs = sorted({p for e in entries for p in (e.get("processes") or [])})

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

            def safe_proto(value: Any) -> str:
                p = str(value).strip().lower() if value else "tcp"
                return p if p in {"tcp", "udp"} else "tcp"

            by_org: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for e in entries:
                org = e.get("asn_org")
                org_txt = org.strip() if isinstance(org, str) and org.strip() else "Unknown network"
                by_org[org_txt].append(e)

            org_blocks: list[str] = []
            for org in sorted(by_org.keys(), key=str.lower):
                def sort_key(x: dict[str, Any]) -> tuple[str, int]:
                    return (x.get("ip") or "", int(x.get("port") or 0))
                org_entries = sorted(by_org[org], key=sort_key)

                lines: list[str] = []
                lines.append(org)

                for e in org_entries:
                    ip = e.get("ip") or "?"
                    port = e.get("port")
                    port_txt = str(int(port)) if isinstance(port, int) else "-"
                    proto = safe_proto(e.get("proto"))
                    procs = sorted(
                        {
                            p for p in (e.get("processes") or [])
                            if isinstance(p, str) and p.strip()
                        }
                    )
                    procs_txt = ", ".join(procs) if procs else "-"

                    def fmt_ip_port(ip_text: str, port_text: str) -> str:
                        if ":" in ip_text and not ip_text.startswith("["):
                            return f"[{ip_text}]:{port_text}"
                        return f"{ip_text}:{port_text}"

                    addr = fmt_ip_port(ip, port_txt)
                    lines.append(f"  {addr} ({proto})")
                    lines.append(f"    Procs: {procs_txt}")
                    lines.append("")

                org_blocks.append("\n".join(lines))

            details[key_str] = f"Location: {place}\n{counts_line}\n\n" + "\n\n".join(org_blocks)

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