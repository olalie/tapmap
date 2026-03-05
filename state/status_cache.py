"""Define cache counters for the TapMap status line.

Accumulate unique items across snapshots and expose these counters:

SOCK: unique sockets (proto, IP, port, PID or process)
SERV: unique services (proto, IP, port)
MAP: public services with valid (lat, lon)
UNM: public services without (lat, lon)
LOC: LAN and loopback services

SERV is derived from SOCK by ignoring PID and process.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypedDict

Proto = str
Ip = str
Port = int
Owner = str

SocketKey = tuple[Proto, Ip, Port, Owner]
ServiceKey = tuple[Proto, Ip, Port]


class StatusCacheItem(TypedDict, total=False):
    """Socket/service fields used by StatusCache.update()."""
    ip: str
    port: int
    proto: str
    pid: int
    process_name: str
    service_scope: str
    lat: float
    lon: float


@dataclass
class StatusCache:
    """Accumulate unique socket and service keys across snapshots."""

    sock: set[SocketKey] = field(default_factory=set)
    serv: set[ServiceKey] = field(default_factory=set)
    map: set[ServiceKey] = field(default_factory=set)
    unm: set[ServiceKey] = field(default_factory=set)
    loc: set[ServiceKey] = field(default_factory=set)

    def clear(self) -> None:
        """Clear cached key sets."""
        self.sock.clear()
        self.serv.clear()
        self.map.clear()
        self.unm.clear()
        self.loc.clear()

    def update(self, cache_items: Sequence[StatusCacheItem]) -> None:
        """Merge snapshot cache_items into the cache.

        Required keys:
            ip: str
            port: int

        Optional keys:
            proto: 'tcp' or 'udp' (default 'tcp')
            pid: int
            process_name: str
            service_scope: 'PUBLIC', 'LAN', 'LOCAL', or 'UNKNOWN'
            lat, lon: numeric coordinates for PUBLIC services
        """
        for item in cache_items:
            ip = item.get("ip")
            if not isinstance(ip, str) or not ip:
                continue

            port_raw = item.get("port")
            try:
                port = int(port_raw)
            except (TypeError, ValueError):
                continue
            if port <= 0:
                continue

            proto = self._normalize_proto(item.get("proto"))

            service_key: ServiceKey = (proto, ip, port)
            self.serv.add(service_key)

            owner = self._owner_label(item.get("pid"), item.get("process_name"))
            socket_key: SocketKey = (proto, ip, port, owner)
            self.sock.add(socket_key)

            scope_u = self._normalize_scope(item.get("service_scope"))

            if scope_u in {"LAN", "LOCAL"}:
                self.loc.add(service_key)
                continue

            if scope_u == "UNKNOWN":
                continue

            if scope_u != "PUBLIC":
                continue

            if self._has_geo(item.get("lat"), item.get("lon")):
                self.map.add(service_key)
            else:
                self.unm.add(service_key)

    def format_chain(self) -> str:
        """Format cache counters for the status line."""
        return (
            f"SOCK {len(self.sock)} "
            f"SERV {len(self.serv)} "
            f"MAP {len(self.map)} "
            f"UNM {len(self.unm)} "
            f"LOC {len(self.loc)}"
        )

    def to_store(self) -> dict[str, Any]:
        """Convert key sets to JSON-friendly lists for Dash stores."""
        return {
            "sock": [list(x) for x in sorted(self.sock)],
            "serv": [list(x) for x in sorted(self.serv)],
            "map": [list(x) for x in sorted(self.map)],
            "unm": [list(x) for x in sorted(self.unm)],
            "loc": [list(x) for x in sorted(self.loc)],
        }

    @classmethod
    def from_store(cls, data: Any) -> StatusCache:
        """Build StatusCache from Dash store data."""
        cache = cls()
        if not isinstance(data, dict):
            return cache

        cache.sock = cls._read_sock(data.get("sock"))
        cache.serv = cls._read_serv(data.get("serv"))
        cache.map = cls._read_serv(data.get("map"))
        cache.unm = cls._read_serv(data.get("unm"))
        cache.loc = cls._read_serv(data.get("loc"))
        return cache

    @staticmethod
    def _normalize_proto(value: Any) -> str:
        p = str(value).lower().strip() if value else "tcp"
        return p if p in {"tcp", "udp"} else "tcp"

    @staticmethod
    def _normalize_scope(value: Any) -> str:
        s = str(value).upper().strip() if isinstance(value, str) else ""
        return s if s in {"PUBLIC", "LAN", "LOCAL"} else "UNKNOWN"

    @staticmethod
    def _has_geo(lat: Any, lon: Any) -> bool:
        return isinstance(lat, (int, float)) and isinstance(lon, (int, float))

    @staticmethod
    def _owner_label(pid: Any, process_name: Any) -> str:
        try:
            pid_i = int(pid)
            if pid_i >= 0:
                return f"pid:{pid_i}"
        except (TypeError, ValueError):
            pass

        name = str(process_name).strip() if process_name else ""
        return f"proc:{name}" if name else "proc:Unknown"

    @staticmethod
    def _read_serv(value: Any) -> set[ServiceKey]:
        if not isinstance(value, list):
            return set()

        out: set[ServiceKey] = set()
        for item in value:
            if not isinstance(item, (list, tuple)) or len(item) != 3:
                continue

            proto, ip, port = item
            p = StatusCache._normalize_proto(proto)

            if not isinstance(ip, str) or not ip:
                continue

            try:
                port_i = int(port)
            except (TypeError, ValueError):
                continue
            if port_i <= 0:
                continue

            out.add((p, ip, port_i))
        return out

    @staticmethod
    def _read_sock(value: Any) -> set[SocketKey]:
        if not isinstance(value, list):
            return set()

        out: set[SocketKey] = set()
        for item in value:
            if not isinstance(item, (list, tuple)) or len(item) != 4:
                continue

            proto, ip, port, owner = item
            p = StatusCache._normalize_proto(proto)

            if not isinstance(ip, str) or not ip:
                continue

            try:
                port_i = int(port)
            except (TypeError, ValueError):
                continue
            if port_i <= 0:
                continue

            owner_s = str(owner).strip() if owner else ""
            owner_s = owner_s if owner_s else "proc:Unknown"

            out.add((p, ip, port_i, owner_s))
        return out

    @staticmethod
    def _safe_str(value: Any) -> str:
        """Return empty string for None, else str(value)."""
        return "" if value is None else str(value)

    @staticmethod
    def _key_ip_port(key: Any) -> tuple[str, int]:
        """Extract (ip, port) sort key from 'ip|port' service key."""
        if not isinstance(key, str):
            return ("", -1)

        ip, _, port_s = key.partition("|")
        try:
            return (ip, int(port_s))
        except ValueError:
            return (ip, -1)

    @staticmethod
    def _format_procs_with_pids(entry: dict[str, Any]) -> str:
        """Format process list with optional PID values."""
        def to_name(v: Any) -> str:
            s = StatusCache._safe_str(v).strip()
            return s

        processes = entry.get("processes")
        names = [to_name(x) for x in processes] if isinstance(processes, list) else []
        names = [n for n in names if n]
        if not names:
            return "-"

        proc_pids_raw = entry.get("proc_pids")
        proc_pids: dict[str, list[int]] = proc_pids_raw if isinstance(proc_pids_raw, dict) else {}

        parts: list[str] = []
        for name in sorted(set(names), key=str.lower):
            pids_raw = proc_pids.get(name)
            pids = (
                sorted({int(x) for x in pids_raw if isinstance(x, int) and x > 0})
                if isinstance(pids_raw, list)
                else []
            )
            if pids:
                parts.append(f"{name} (pid {', '.join(str(x) for x in pids)})")
            else:
                parts.append(name)

        return ", ".join(parts) if parts else "-"

    def show_ui_cache(self, ui_cache: dict[str, Any], *, title: str = "UI CACHE") -> None:
        """Show UI cache snapshot in terminal log."""
        logger = logging.getLogger("tapmap.cache")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cache = ui_cache if isinstance(ui_cache, dict) else {}

        lines: list[str] = []
        lines.append(f"\n{title} ({ts})")
        lines.append(f"CACHE: {self.format_chain()}")
        lines.append(f"Cache entries: {len(cache)}")

        if not cache:
            logger.info("\n".join(lines))
            return

        for key in sorted(cache.keys(), key=self._key_ip_port):
            entry = cache.get(key)
            if not isinstance(entry, dict):
                continue

            ip = self._safe_str(entry.get("ip")) or self._safe_str(key).split("|", 1)[0]

            port = entry.get("port")
            port_txt = str(int(port)) if isinstance(port, int) else "-"

            proto = self._normalize_proto(entry.get("proto"))

            asn_org = self._safe_str(entry.get("asn_org")) or "-"
            city = self._safe_str(entry.get("city")) or ""
            country = self._safe_str(entry.get("country")) or ""
            place = ", ".join([x for x in [city, country] if x]) or "-"

            procs_txt = self._format_procs_with_pids(entry)

            addr = f"{ip}:{port_txt}"
            lines.append(
                f"{addr:<22} ({proto})  procs={procs_txt}  {asn_org}  place={place}"
            )
        logger.info("\n".join(lines))
