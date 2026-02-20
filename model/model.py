from __future__ import annotations

import ipaddress
import logging
import socket
from datetime import datetime
from typing import Any, Final, TypedDict


class OpenPort(TypedDict):
    """Define one row for the Open Ports modal table."""

    proto: str
    local_address: str
    service: str
    service_hint: str | None
    process_label: str
    process_hint: str
    process_status: str
    pid: int | None
    scope: str


class SnapshotPayload(TypedDict):
    """Define the payload from Model.snapshot()."""

    error: bool
    stats: dict[str, Any]
    cache_items: list[dict[str, Any]]
    map_candidates: list[dict[str, Any]]
    open_ports: list[OpenPort]


class Model:
    """Build a live snapshot for the UI.

    Treat as stateless; caching and aggregation over time occur in the UI.

    Returned keys:
        stats:
            Live counters for the status line: CON, EST, LST, online, updated.
            LST counts TCP sockets in state LISTEN.
        cache_items:
            ESTABLISHED endpoints with a remote address (includes local and non-geo).
            Used to build the CACHE chain and the Unknown modal.
        map_candidates:
            Subset of cache_items: external endpoints with valid geolocation.
        open_ports:
            Local open ports for the modal table.
            Includes TCP LISTEN sockets and UDP sockets bound to a local port.

    On failure, returns {"error": True, ...} and empty lists.
    """

    INTERNET_TARGETS: Final[tuple[tuple[str, int], ...]] = (("1.1.1.1", 53), ("8.8.8.8", 53))

    def __init__(self, netinfo: Any, geoinfo: Any) -> None:
        self.netinfo = netinfo
        self.geoinfo = geoinfo
        self.logger = logging.getLogger(__name__)

    def snapshot(self) -> SnapshotPayload:
        """Return a snapshot payload for the UI."""
        now = datetime.now()
        geo_enabled = self._geoinfo_enabled()

        try:
            online = self._has_internet()
            connections = self.netinfo.get_data()

            if geo_enabled:
                self.geoinfo.enrich(connections)

            live_con = 0
            live_est = 0
            live_lst = 0
            dropped_missing_remote = 0

            cache_items: list[dict[str, Any]] = []
            map_candidates: list[dict[str, Any]] = []
            open_ports: list[OpenPort] = []

            for conn in connections:
                if not isinstance(conn, dict):
                    continue

                proto = str(conn.get("proto") or "tcp").lower()
                status = conn.get("status")

                if proto == "tcp":
                    live_con += 1

                if proto == "tcp" and status == "LISTEN":
                    live_lst += 1
                    item = self._build_open_port(conn, proto="tcp")
                    if item is not None:
                        open_ports.append(item)
                    continue

                if proto == "udp":
                    item = self._build_open_port(conn, proto="udp")
                    if item is not None:
                        open_ports.append(item)
                    continue

                if proto == "tcp" and status == "ESTABLISHED":
                    live_est += 1
                    item = self._build_established_item(conn)
                    if item is None:
                        dropped_missing_remote += 1
                        continue

                    cache_items.append(item)

                    lat = item.get("lat")
                    lon = item.get("lon")
                    has_geo = isinstance(lat, (int, float)) and isinstance(lon, (int, float))
                    if (not item["is_local"]) and has_geo:
                        map_candidates.append(item)

            return {
                "error": False,
                "stats": {
                    "online": online,
                    "live_con": live_con,
                    "live_est": live_est,
                    "live_lst": live_lst,
                    "updated": now.strftime("%H:%M:%S"),
                    "dropped_missing_remote": dropped_missing_remote,
                    "geoinfo_enabled": geo_enabled,
                },
                "cache_items": cache_items,
                "map_candidates": map_candidates,
                "open_ports": open_ports,
            }

        except Exception as exc:
            self.logger.error("Error in Model.snapshot(): %s", exc)
            return {
                "error": True,
                "stats": {
                    "online": False,
                    "live_con": 0,
                    "live_est": 0,
                    "live_lst": 0,
                    "updated": now.strftime("%H:%M:%S"),
                    "dropped_missing_remote": 0,
                    "geoinfo_enabled": geo_enabled,
                },
                "cache_items": [],
                "map_candidates": [],
                "open_ports": [],
            }

    def _geoinfo_enabled(self) -> bool:
        """Return True if geolocation enrichment is enabled."""
        return bool(getattr(self.geoinfo, "enabled", False))

    @staticmethod
    def _is_local_ip(ip: str) -> bool:
        """Return True for IPs excluded from geolocation and mapping."""
        try:
            addr = ipaddress.ip_address(ip)
            return addr.is_private or addr.is_loopback or addr.is_link_local
        except ValueError:
            return False

    def _has_internet(self, timeout_s: float = 0.6) -> bool:
        """Return True if at least one internet target is reachable within timeout_s."""
        for host, port in self.INTERNET_TARGETS:
            try:
                with socket.create_connection((host, port), timeout=timeout_s):
                    return True
            except OSError:
                continue
        return False

    @staticmethod
    def _get_scope(ip: str | None) -> str:
        """Return a coarse exposure scope from the bound local IP address.

        LOCAL: loopback only
        LAN: private or link-local
        PUBLIC: wildcard bind or public IP
        UNKNOWN: missing or invalid IP
        """
        if not ip:
            return "UNKNOWN"

        if ip in ("0.0.0.0", "::"):
            return "PUBLIC"

        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return "UNKNOWN"

        if addr.is_loopback:
            return "LOCAL"

        if addr.is_private or addr.is_link_local:
            return "LAN"

        return "PUBLIC"

    @staticmethod
    def _format_local_address(ip: str | None, port: int | None) -> str:
        """Return a stable local address string for UI display."""
        ip_str = ip or ""
        if port is None:
            return ip_str

        if ":" in ip_str and not ip_str.startswith("["):
            ip_str = f"[{ip_str}]"

        return f"{ip_str}:{int(port)}"

    @staticmethod
    def _process_hint(conn: dict[str, Any]) -> str | None:
        """Return a single-line hint from cmdline or exe."""
        cmdline = conn.get("cmdline")
        if isinstance(cmdline, list) and cmdline:
            text = " ".join(str(x) for x in cmdline if x is not None).strip()
            if text:
                return text

        exe = conn.get("exe")
        return exe if isinstance(exe, str) and exe else None

    @staticmethod
    def _service_name(port: int, proto: str) -> str:
        """Return a well-known service name for port and proto, or 'Unknown'."""
        try:
            name = socket.getservbyport(int(port), proto.lower())
            return name if name else "Unknown"
        except OSError:
            return "Unknown"

    def _build_open_port(self, conn: dict[str, Any], *, proto: str) -> OpenPort | None:
        """Return one OpenPort item for the modal table.

        Fields:
            process_label: name if available, otherwise process_status
            process_hint: exe path if available, otherwise process_status
            service: well-known port name, or 'Unknown'
        """
        l_ip = conn.get("laddr_ip")
        l_port_obj = conn.get("laddr_port")
        if l_port_obj is None:
            return None

        try:
            l_port = int(l_port_obj)
        except (TypeError, ValueError):
            return None

        local_address = self._format_local_address(l_ip, l_port)

        process_status = conn.get("process_status")
        if not isinstance(process_status, str) or not process_status:
            process_status = "Unavailable"

        process_name = conn.get("process_name")
        if not isinstance(process_name, str) or not process_name:
            process_name = None

        exe = conn.get("exe")
        if not isinstance(exe, str) or not exe:
            exe = None

        process_label = process_name or process_status
        process_hint = exe or process_status

        service = self._service_name(l_port, proto)
        if not isinstance(service, str) or not service:
            service = "Unknown"

        service_hint = None
        if service == "Unknown":
            service_hint = "Not in system service table"

        return {
            "proto": proto,
            "local_address": local_address,
            "service": service,
            "service_hint": service_hint,
            "process_label": process_label,
            "process_hint": process_hint,
            "process_status": process_status,
            "pid": conn.get("pid"),
            "scope": self._get_scope(l_ip),
        }

    def _build_established_item(self, conn: dict[str, Any]) -> dict[str, Any] | None:
        """Build one cache item from an ESTABLISHED TCP connection."""
        remote_ip = conn.get("raddr_ip")
        remote_port = conn.get("raddr_port")
        if not remote_ip or remote_port is None:
            return None

        try:
            port = int(remote_port)
        except (TypeError, ValueError):
            return None

        service = self._service_name(port, "tcp")
        service_hint = "Not in system service table" if service == "Unknown" else None
        is_local = self._is_local_ip(remote_ip)
        lat = conn.get("lat")
        lon = conn.get("lon")
        has_geo = isinstance(lat, (int, float)) and isinstance(lon, (int, float))

        return {
            "ip": remote_ip,
            "port": port,
            "service": service,
            "service_hint": service_hint,
            "is_local": is_local,
            "lat": float(lat) if has_geo else None,
            "lon": float(lon) if has_geo else None,
            "pid": conn.get("pid"),
            "process_name": conn.get("process_label"),
            "exe": conn.get("exe"),
            "cmdline": conn.get("cmdline"),
            "process_status": conn.get("process_status"),
            "city": conn.get("city"),
            "country": conn.get("country"),
            "asn": conn.get("asn"),
            "asn_org": conn.get("asn_org"),
        }

    def _service_name(self, port: int, proto: str) -> str:
        try:
            return socket.getservbyport(int(port), proto.lower())
        except OSError:
            return "Unknown"