"""Define cache and view building for TapMap.

Merge map candidates into a per-IP cache, group cached entries by rounded
coordinates, and build hover summaries and click details for the UI.
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
        self.debug = debug
        self.logger = logging.getLogger(__name__)

    def merge_map_candidates(
        self,
        ui_cache: dict[str, Any],
        map_candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Merge map candidates into a per-IP cache.

        Key entries by IP and accumulate ports and process names across snapshots.
        Store values in JSON-friendly lists.
        """
        cache = dict(ui_cache) if isinstance(ui_cache, dict) else {}

        for candidate in map_candidates:
            ip = candidate.get("ip")
            if not isinstance(ip, str) or not ip:
                continue

            port = candidate.get("port")
            process_name = candidate.get("process_name") or "Unknown"

            entry = cache.get(ip)
            if not isinstance(entry, dict):
                entry = {
                    "ip": ip,
                    "lon": candidate.get("lon"),
                    "lat": candidate.get("lat"),
                    "city": candidate.get("city"),
                    "country": candidate.get("country"),
                    "asn": candidate.get("asn"),
                    "asn_org": candidate.get("asn_org"),
                    "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "ports": [],
                    "processes": [],
                }
                cache[ip] = entry

            ports_set = set(entry.get("ports") or [])
            procs_set = set(entry.get("processes") or [])

            if isinstance(port, int):
                ports_set.add(port)

            if isinstance(process_name, str) and process_name:
                procs_set.add(process_name)

            entry["ports"] = sorted(ports_set)
            entry["processes"] = sorted(procs_set)

            # Candidate updates may arrive after the initial cache entry.
            for key in ("lon", "lat", "city", "country", "asn", "asn_org"):
                if entry.get(key) is None and candidate.get(key) is not None:
                    entry[key] = candidate.get(key)

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
        """Group cached IP entries by rounded coordinates.

        Collapse overlapping endpoints into one marker per coordinate group.

        Result format:
            {
            "points": [(lon, lat), ...],
            "summaries": {"0": "...", "1": "..."},
            "details": {"0": "...", "1": "..."},
            }
        """
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

            # --- Place name ---
            cities = [e.get("city") for e in entries if e.get("city")]
            countries = [e.get("country") for e in entries if e.get("country")]

            city = Counter(cities).most_common(1)[0][0] if cities else None
            country = Counter(countries).most_common(1)[0][0] if countries else None

            endpoint_count = len(entries)

            if city and country:
                place = f"{city}, {country}"
            elif country:
                place = country
            else:
                place = "Unknown place name"

            line1 = f"{place} ({endpoint_count} endpoints)" if endpoint_count > 1 else place

            # --- Networks ---
            unique_orgs = sorted({e.get("asn_org") for e in entries if e.get("asn_org")})
            if len(unique_orgs) == 1:
                line2 = unique_orgs[0]
            elif not unique_orgs:
                line2 = "Unknown network"
            else:
                line2 = f"Multiple networks ({len(unique_orgs)})"

            # --- Ports and processes (for summary) ---
            unique_ports = sorted({int(p) for e in entries for p in (e.get("ports") or [])})
            unique_procs = sorted({p for e in entries for p in (e.get("processes") or [])})

            ports_txt = self.format_list_compact([str(p) for p in unique_ports], max_items=3)
            procs_txt = self.format_list_compact(unique_procs, max_items=2)
            line3 = f"Ports: {ports_txt} | Procs: {procs_txt}"

            key_str = str(idx)
            summaries[key_str] = f"{line1}<br>{line2}<br>{line3}"

            # --- Detail section ---

            # Unique counts
            unique_ips = sorted({e.get("ip") for e in entries if e.get("ip")})
            counts_line = (
                f"Endpoints: {endpoint_count} | "
                f"Networks: {len(unique_orgs)} | "
                f"IPs: {len(unique_ips)} | "
                f"Ports: {len(unique_ports)} | "
                f"Procs: {len(unique_procs)}"
            )

            # Per-endpoint blocks
            ip_lines: list[str] = []
            for e in sorted(entries, key=lambda x: x.get("ip") or ""):
                ip = e.get("ip") or "?"
                e_org = e.get("asn_org") or "?"
                e_ports = sorted({int(p) for p in (e.get("ports") or [])})
                e_procs = sorted({p for p in (e.get("processes") or [])})

                ip_lines.append(
                    f"{ip}  {e_org}\n"
                    f"  Ports: {', '.join(str(p) for p in e_ports) if e_ports else '-'}\n"
                    f"  Procs: {', '.join(e_procs) if e_procs else '-'}"
                )

            details[key_str] = f"Location: {place}\n{counts_line}\n\n" + "\n\n".join(ip_lines)

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
            lon = entry.get("lon")
            lat = entry.get("lat")
            if lon is None or lat is None:
                continue
            coords.append(
                (
                    round(float(lon), self.coord_precision),
                    round(float(lat), self.coord_precision),
                )
            )

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