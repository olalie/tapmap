from __future__ import annotations

import ipaddress
import logging
import socket
from datetime import datetime
from typing import Any, Final, TypedDict


class CacheItem(TypedDict):
    """Define one cache item for the UI."""
    proto: str
    ip: str
    port: int
    service: str
    service_hint: str | None
    is_local: bool
    lat: float | None
    lon: float | None
    pid: int | None
    process_name: str | None
    exe: str | None
    cmdline: list[str] | None
    process_status: str | None
    city: str | None
    country: str | None
    asn: str | None
    asn_org: str | None


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
    cache_items: list[CacheItem]
    map_candidates: list[CacheItem]
    open_ports: list[OpenPort]


class Model:
    """Build a live snapshot for the UI.

    Treat as stateless; caching and aggregation over time occur in the UI.

    Returned keys:
        stats:
            Live counters for the status line and snapshot metadata.
            Keys:
                online
                live_tcp_total
                live_tcp_established
                live_tcp_listen
                live_udp_remote
                live_udp_bound
                updated
                dropped_missing_remote
                geoinfo_enabled
        cache_items:
            Remote services from the snapshot:
                TCP: ESTABLISHED with remote address
                UDP: remote peer present (if available in backend)
            Includes LAN/LOCAL and unmapped services.
        map_candidates:
            Subset of cache_items: PUBLIC services with valid geolocation.
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

            live_tcp_total = 0
            live_tcp_established = 0
            live_tcp_listen = 0
            live_udp_remote = 0
            live_udp_bound = 0
            dropped_missing_remote = 0

            cache_items: list[CacheItem] = []
            map_candidates: list[CacheItem] = []
            open_ports: list[OpenPort] = []

            for conn in connections:
                if not isinstance(conn, dict):
                    continue

                proto = str(conn.get("proto") or "tcp").lower()
                status = conn.get("status")

                if proto == "tcp":
                    live_tcp_total += 1

                    if status == "ESTABLISHED":
                        live_tcp_established += 1
                        item = self._build_remote_endpoint_item(conn, proto="tcp")
                        if item is None:
                            dropped_missing_remote += 1
                            continue

                        cache_items.append(item)
                        if self._is_map_candidate(item):
                            map_candidates.append(item)
                        continue

                    if status == "LISTEN":
                        live_tcp_listen += 1
                        open_item = self._build_open_port(conn, proto="tcp")
                        if open_item is not None:
                            open_ports.append(open_item)
                        continue

                    continue

                if proto == "udp":
                    item = self._build_remote_endpoint_item(conn, proto="udp")
                    if item is not None:
                        live_udp_remote += 1
                        cache_items.append(item)
                        if self._is_map_candidate(item):
                            map_candidates.append(item)
                        continue

                    live_udp_bound += 1
                    open_item = self._build_open_port(conn, proto="udp")
                    if open_item is not None:
                        open_ports.append(open_item)
                    continue

            return {
                "error": False,
                "stats": {
                    "online": online,
                    "live_tcp_total": live_tcp_total,
                    "live_tcp_established": live_tcp_established,
                    "live_tcp_listen": live_tcp_listen,
                    "live_udp_remote": live_udp_remote,
                    "live_udp_bound": live_udp_bound,
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
                    "live_tcp_total": 0,
                    "live_tcp_established": 0,
                    "live_tcp_listen": 0,
                    "live_udp_remote": 0,
                    "live_udp_bound": 0,
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

    @staticmethod
    def _is_map_candidate(item: CacheItem) -> bool:
        """Return True if the cache item is a PUBLIC service with valid geolocation."""
        if item.get("is_local"):
            return False
        lat = item.get("lat")
        lon = item.get("lon")
        return isinstance(lat, (int, float)) and isinstance(lon, (int, float))

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
    def _service_name(port: int, proto: str) -> str:
        """Return a well-known service name for port and proto, or 'Unknown'."""
        try:
            name = socket.getservbyport(int(port), proto.lower())
            return name if name else "Unknown"
        except OSError:
            return "Unknown"

    def _build_open_port(self, conn: dict[str, Any], *, proto: str) -> OpenPort | None:
        """Build one OpenPort item for the Open Ports modal table."""
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
        service_hint = "Not in system service table" if service == "Unknown" else None

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

    def _build_remote_endpoint_item(self, conn: dict[str, Any], *, proto: str) -> CacheItem | None:
        """Build one cache item from a remote service.

        Returns None if the backend does not provide a remote peer.
        """
        proto_norm = str(proto).lower() or "tcp"

        remote_ip = conn.get("raddr_ip")
        remote_port = conn.get("raddr_port")
        if not remote_ip or remote_port is None:
            return None

        try:
            port = int(remote_port)
        except (TypeError, ValueError):
            return None

        service = self._service_name(port, proto_norm)
        service_hint = "Not in system service table" if service == "Unknown" else None

        is_local = self._is_local_ip(remote_ip)

        lat = conn.get("lat")
        lon = conn.get("lon")
        has_geo = isinstance(lat, (int, float)) and isinstance(lon, (int, float))
        lat_value = float(lat) if has_geo else None
        lon_value = float(lon) if has_geo else None

        return {
            "proto": proto_norm,
            "ip": remote_ip,
            "port": port,
            "service": service,
            "service_hint": service_hint,
            "is_local": is_local,
            "lat": lat_value,
            "lon": lon_value,
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

