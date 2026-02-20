"""Define status cache for the TapMap status line.

Track unique remote endpoints over time and build the
EST - LOC - NON_GEO = GEO -> RIP -> RLOC chain.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class StatusCache:
    """Accumulate endpoint statistics across snapshots.

    All sets use unique keys:
    - est, loc, non_geo, geo: (ip, port)
    - rip: ip
    - rloc: (lat, lon)
    """

    est: set[tuple[str, int]] = field(default_factory=set)
    loc: set[tuple[str, int]] = field(default_factory=set)
    non_geo: set[tuple[str, int]] = field(default_factory=set)
    geo: set[tuple[str, int]] = field(default_factory=set)
    rip: set[str] = field(default_factory=set)
    rloc: set[tuple[float, float]] = field(default_factory=set)

    def clear(self) -> None:
        """Clear all accumulated sets."""
        self.est.clear()
        self.loc.clear()
        self.non_geo.clear()
        self.geo.clear()
        self.rip.clear()
        self.rloc.clear()

    def update(self, cache_items: list[dict[str, Any]]) -> None:
        """Merge a snapshot into the cache.

        cache_items contains established endpoints with keys such as:
        ip, port, is_local, lat, lon.
        """
        for item in cache_items:
            ip = item.get("ip")
            port = item.get("port")
            if not ip or not isinstance(port, int):
                continue

            key = (ip, port)
            self.est.add(key)

            if item.get("is_local"):
                self.loc.add(key)
                continue

            lat = item.get("lat")
            lon = item.get("lon")
            if lat is None or lon is None:
                self.non_geo.add(key)
                continue

            # External endpoint with valid geo
            self.geo.add(key)
            self.rip.add(ip)
            self.rloc.add((float(lat), float(lon)))

    def to_store(self) -> dict[str, Any]:
        """Convert internal sets to JSON-friendly lists for Dash dcc.Store."""
        return {
            "est": sorted(self.est),
            "loc": sorted(self.loc),
            "non_geo": sorted(self.non_geo),
            "geo": sorted(self.geo),
            "rip": sorted(self.rip),
            "rloc": sorted(self.rloc),
        }

    @classmethod
    def from_store(cls, data: Any) -> StatusCache:
        """Create a StatusCache from Dash store data."""
        cache = cls()
        if not isinstance(data, dict):
            return cache

        def _pairs(value: Any) -> set[tuple[str, int]]:
            if not isinstance(value, list):
                return set()

            out: set[tuple[str, int]] = set()
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

        cache.est = _pairs(data.get("est"))
        cache.loc = _pairs(data.get("loc"))
        cache.non_geo = _pairs(data.get("non_geo"))
        cache.geo = _pairs(data.get("geo"))

        rip_val = data.get("rip")
        cache.rip = {str(x) for x in rip_val} if isinstance(rip_val, list) else set()

        rloc_val = data.get("rloc")
        if isinstance(rloc_val, list):
            for item in rloc_val:
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    continue
                lat, lon = item
                if lat is None or lon is None:
                    continue
                try:
                    cache.rloc.add((float(lat), float(lon)))
                except (TypeError, ValueError):
                    continue

        return cache

    def format_chain(self, rloc_map: int | None = None) -> str:
        """Format the status chain for the UI.

        Args:
            rloc_map: Number of remote location groups shown on the map.
        """
        est = len(self.est)
        loc = len(self.loc)
        non_geo = len(self.non_geo)
        geo = len(self.geo)
        rip = len(self.rip)

        rloc = rloc_map if rloc_map is not None else len(self.rloc)

        return f"EST {est} - LOC {loc} - NON_GEO {non_geo} = GEO {geo} -> RIP {rip} -> RLOC {rloc}"

    def log_cache(self, ui_cache: dict[str, Any], *, title: str = "CACHE SNAPSHOT") -> None:
        """Log a readable cache snapshot.

        Args:
            ui_cache: UI cache keyed by IP.
            title: Header title for the log block.
        """
        logger = logging.getLogger("tapmap.cache")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines: list[str] = []
        lines.append(f"\n===== {title} ({ts}) =====")
        lines.append(self.format_chain())

        cache = ui_cache if isinstance(ui_cache, dict) else {}
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

        # Keep output stable across runs.
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
