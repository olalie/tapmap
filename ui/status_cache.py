"""Define cache counters for the TapMap status line.

Accumulate unique endpoints across snapshots and expose four counters:

END: cached endpoints (ip, port)
MAP: public endpoints with valid (lat, lon)
UNM: public endpoints without (lat, lon)
LOC: LAN and loopback endpoints
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

EndpointKey = tuple[str, int]


@dataclass
class StatusCache:
    """Accumulate unique endpoints across snapshots.

    Store unique keys:
        end, map, unm, loc: (ip, port)
    """

    end: set[EndpointKey] = field(default_factory=set)
    map: set[EndpointKey] = field(default_factory=set)
    unm: set[EndpointKey] = field(default_factory=set)
    loc: set[EndpointKey] = field(default_factory=set)

    def clear(self) -> None:
        """Clear cached endpoint sets."""
        self.end.clear()
        self.map.clear()
        self.unm.clear()
        self.loc.clear()

    def update(self, cache_items: list[dict[str, Any]]) -> None:
        """Merge snapshot items into the cache.

        Require keys:
            ip: str
            port: int

        Optional keys:
            is_local: truthy for LAN or loopback
            lat, lon: numeric coordinates for public endpoints
        """
        for item in cache_items:
            ip = item.get("ip")
            port = item.get("port")
            if not ip or not isinstance(port, int):
                continue

            key: EndpointKey = (ip, port)
            self.end.add(key)

            if item.get("is_local"):
                self.loc.add(key)
                continue

            lat = item.get("lat")
            lon = item.get("lon")
            has_geo = isinstance(lat, (int, float)) and isinstance(lon, (int, float))
            if not has_geo:
                self.unm.add(key)
                continue

            self.map.add(key)

    def to_store(self) -> dict[str, Any]:
        """Convert sets to JSON friendly lists for Dash stores."""
        return {
            "end": sorted(self.end),
            "map": sorted(self.map),
            "unm": sorted(self.unm),
            "loc": sorted(self.loc),
        }

    @classmethod
    def from_store(cls, data: Any) -> StatusCache:
        """Build StatusCache from Dash store data."""
        cache = cls()
        if not isinstance(data, dict):
            return cache

        def _endpoint_pairs(value: Any) -> set[EndpointKey]:
            if not isinstance(value, list):
                return set()

            out: set[EndpointKey] = set()
            for item in value:
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    continue
                ip, port = item
                if not ip or port is None:
                    continue
                try:
                    out.add((str(ip), int(port)))
                except (TypeError, ValueError):
                    continue
            return out

        cache.end = _endpoint_pairs(data.get("end"))
        cache.map = _endpoint_pairs(data.get("map"))
        cache.unm = _endpoint_pairs(data.get("unm"))
        cache.loc = _endpoint_pairs(data.get("loc"))
        return cache

    def format_chain(self) -> str:
        """Format counters for the status line."""
        end = len(self.end)
        map_ = len(self.map)
        unm = len(self.unm)
        loc = len(self.loc)
        return f"END {end} MAP {map_} UNM {unm} LOC {loc}"

    def log_cache(self, ui_cache: dict[str, Any], *, title: str = "UI CACHE") -> None:
        """Log a readable cache snapshot."""
        logger = logging.getLogger("tapmap.cache")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cache = ui_cache if isinstance(ui_cache, dict) else {}

        lines: list[str] = []
        lines.append(f"\n===== {title} ({ts}) =====")
        lines.append(f"CACHE: {self.format_chain()}")
        lines.append(f"Cache entries: {len(cache)}")

        if not cache:
            logger.info("\n".join(lines))
            return

        def safe_str(v: Any) -> str:
            return "" if v is None else str(v)

        def safe_int(v: Any) -> int:
            try:
                return int(v)
            except (TypeError, ValueError):
                return -1

        def ports_text(entry: dict[str, Any]) -> str:
            ports = entry.get("ports")
            if isinstance(ports, list):
                ps = [safe_int(x) for x in ports]
                ps = sorted({p for p in ps if p >= 0})
                return ",".join(str(p) for p in ps) if ps else "-"
            return "-"

        def procs_text(entry: dict[str, Any]) -> str:
            procs = entry.get("processes")
            if isinstance(procs, list):
                ps = sorted({safe_str(x) for x in procs if safe_str(x)})
                return ", ".join(ps) if ps else "-"
            return "-"

        # Stable output across polls.
        for ip in sorted(cache.keys(), key=lambda s: str(s)):
            entry = cache.get(ip)
            if not isinstance(entry, dict):
                continue

            asn_org = safe_str(entry.get("asn_org")) or "-"
            city = safe_str(entry.get("city")) or ""
            country = safe_str(entry.get("country")) or ""
            place = ", ".join([x for x in [city, country] if x]) or "-"

            lines.append(
                f"{ip:<40}  {asn_org}  place={place}  "
                f"ports={ports_text(entry)}  procs={procs_text(entry)}"
            )

        logger.info("\n".join(lines))
