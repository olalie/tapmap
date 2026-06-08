"""Aggregate socket records across all network namespaces (Linux).

The default psutil backend only sees the network namespace tapmap runs in. When
tapmap runs as a Docker container with ``pid: host``, every host PID is visible,
including the main process of each *other* container. The connection table of a
namespace can be read from ``/proc/<pid>/net/{tcp,tcp6,udp,udp6}`` for any pid in
that namespace, so this backend:

1. Delegates to :class:`PsutilNetInfo` for the host/default namespace (preserving
   full process attribution there), then
2. Parses ``/proc/<pid>/net/*`` for every *other* namespace, labeling those rows
   by the owning container.

Opt-in only (``TAPMAP_CAPTURE_ALL_NETNS=1``); on any failure it degrades to the
plain host-only psutil result.
"""

from __future__ import annotations

import os
import re
import socket
import struct
from typing import Any

from .netinfo_psutil import PsutilNetInfo

# /proc/net/tcp "st" column (hex) -> psutil-compatible status string.
_TCP_STATES = {
    "01": "ESTABLISHED",
    "02": "SYN_SENT",
    "03": "SYN_RECV",
    "04": "FIN_WAIT1",
    "05": "FIN_WAIT2",
    "06": "TIME_WAIT",
    "07": "CLOSE",
    "08": "CLOSE_WAIT",
    "09": "LAST_ACK",
    "0A": "LISTEN",
    "0B": "CLOSING",
}

# Per-protocol /proc/net file -> (proto, family, socket type string).
_PROC_NET_FILES = (
    ("tcp", "IPv4", "1"),
    ("tcp6", "IPv6", "1"),
    ("udp", "IPv4", "2"),
    ("udp6", "IPv6", "2"),
)

_CGROUP_DOCKER_RE = re.compile(r"docker[-/]([0-9a-f]{12,64})")


class NetNsNetInfo:
    """Collect socket records across the host plus every container namespace."""

    def __init__(self, allowed_statuses: set[str] | None = None) -> None:
        self.allowed_statuses = allowed_statuses
        self._host = PsutilNetInfo(allowed_statuses=allowed_statuses)

    def get_data(self) -> list[dict[str, Any]]:
        """Return host records plus per-container records, or host-only on error."""
        host_records = self._host.get_data()
        try:
            container_records = self._collect_container_records()
        except Exception:
            # Never let namespace scanning break the existing host capture.
            return host_records
        return host_records + container_records

    # -- namespace discovery ------------------------------------------------

    def _collect_container_records(self) -> list[dict[str, Any]]:
        host_inode = self._netns_inode(os.getpid())
        groups = self._group_pids_by_netns(skip_inode=host_inode)
        if not groups:
            return []

        names = self._docker_names()
        results: list[dict[str, Any]] = []

        for inode, pids in groups.items():
            for pid in pids:
                records = self._read_netns(pid)
                if records is None:
                    continue  # unreadable pid; try the next one in this netns
                label = self._label_for(pid, names, inode)
                for rec in records:
                    rec["process_label"] = label
                    rec["process_name"] = label
                results.extend(records)
                break  # one readable pid per netns yields the whole table

        return results

    def _group_pids_by_netns(self, *, skip_inode: int | None) -> dict[int, list[int]]:
        """Map netns inode -> sorted pids, excluding the host namespace."""
        groups: dict[int, list[int]] = {}
        try:
            entries = os.scandir("/proc")
        except OSError:
            return groups

        with entries:
            for entry in entries:
                if not entry.name.isdigit():
                    continue
                pid = int(entry.name)
                inode = self._netns_inode(pid)
                if inode is None or inode == skip_inode:
                    continue
                groups.setdefault(inode, []).append(pid)

        for pids in groups.values():
            pids.sort()  # lowest pid first -> cleanest cgroup for labeling
        return groups

    @staticmethod
    def _netns_inode(pid: int) -> int | None:
        """Return the network-namespace inode for a pid, or None if unreadable."""
        try:
            return os.stat(f"/proc/{pid}/ns/net").st_ino
        except (PermissionError, FileNotFoundError, ProcessLookupError, OSError):
            return None

    # -- /proc/net parsing --------------------------------------------------

    def _read_netns(self, pid: int) -> list[dict[str, Any]] | None:
        """Parse a pid's four /proc/net files. None if the whole netns is unreadable."""
        records: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        readable = False

        for fname, family, sock_type in _PROC_NET_FILES:
            try:
                with open(f"/proc/{pid}/net/{fname}", encoding="ascii") as fh:
                    lines = fh.readlines()
            except (PermissionError, FileNotFoundError, ProcessLookupError, OSError):
                continue
            readable = True

            proto = "tcp" if fname.startswith("tcp") else "udp"
            for line in lines[1:]:
                rec = self._parse_line(line, proto=proto, family=family, sock_type=sock_type)
                if rec is None:
                    continue
                if not self._is_included(proto, rec["status"]):
                    continue
                key = (
                    proto,
                    family,
                    rec["laddr_ip"],
                    rec["laddr_port"],
                    rec["raddr_ip"],
                    rec["raddr_port"],
                )
                if key in seen:
                    continue
                seen.add(key)
                rec["pid"] = pid
                records.append(rec)

        return records if readable else None

    def _parse_line(
        self, line: str, *, proto: str, family: str, sock_type: str
    ) -> dict[str, Any] | None:
        parts = line.split()
        if len(parts) < 4:
            return None

        l_ip, l_port = self._parse_addr(parts[1], family)
        if l_port is None:
            return None
        r_ip, r_port = self._parse_addr(parts[2], family)

        if proto == "tcp":
            status = _TCP_STATES.get(parts[3].upper(), "NONE")
        else:
            status = "NONE"

        out_family = family
        # IPv4-mapped IPv6 (::ffff:a.b.c.d) -> report as plain IPv4 so it matches
        # and dedups against psutil host rows.
        if family == "IPv6":
            l_ip, out_family = self._demap(l_ip, out_family)
            r_ip, out_family = self._demap(r_ip, out_family)

        return {
            "pid": None,
            "proto": proto,
            "status": status,
            "family": out_family,
            "type": sock_type,
            "laddr_ip": l_ip,
            "laddr_port": l_port,
            "raddr_ip": r_ip,
            "raddr_port": r_port,
            "process_status": "OK",
            "process_label": None,  # filled in by the caller with the container label
            "process_name": None,
            "exe": None,
            "cmdline": None,
        }

    @staticmethod
    def _demap(ip: str | None, family: str) -> tuple[str | None, str]:
        if ip and ip.startswith("::ffff:") and "." in ip:
            return ip[len("::ffff:") :], "IPv4"
        return ip, family

    @staticmethod
    def _parse_addr(token: str, family: str) -> tuple[str | None, int | None]:
        """Decode a HEXIP:HEXPORT token from /proc/net into (ip, port)."""
        if ":" not in token:
            return None, None
        hex_ip, _, hex_port = token.rpartition(":")
        try:
            port = int(hex_port, 16)
        except ValueError:
            return None, None

        try:
            if family == "IPv4":
                raw = bytes.fromhex(hex_ip)[::-1]  # little-endian 32-bit word
                ip = socket.inet_ntop(socket.AF_INET, raw)
            else:
                # Four little-endian 32-bit words; byte-reverse each word.
                words = struct.unpack("<4I", bytes.fromhex(hex_ip))
                raw = struct.pack(">4I", *words)
                ip = socket.inet_ntop(socket.AF_INET6, raw)
        except (ValueError, OSError):
            return None, None

        # All-zero address == unbound/no remote -> no endpoint.
        if port == 0 and ip in ("0.0.0.0", "::"):
            return None, None
        if ip in ("0.0.0.0", "::"):
            ip = None
        return ip, port

    # -- container labeling -------------------------------------------------

    def _label_for(self, pid: int, names: dict[str, str], inode: int) -> str:
        cid = self._container_id(pid)
        if cid is None:
            return f"netns:{inode}"
        short = cid[:12]
        return names.get(cid) or names.get(short) or f"docker:{short}"

    @staticmethod
    def _container_id(pid: int) -> str | None:
        try:
            with open(f"/proc/{pid}/cgroup", encoding="ascii") as fh:
                text = fh.read()
        except (PermissionError, FileNotFoundError, ProcessLookupError, OSError):
            return None
        match = _CGROUP_DOCKER_RE.search(text)
        return match.group(1) if match else None

    @staticmethod
    def _docker_names() -> dict[str, str]:
        """Map container id (full and 12-char) -> friendly name via the Docker UDS.

        Returns an empty map (so labels fall back to short ids) if the socket is
        absent or unreachable.
        """
        sock_path = "/var/run/docker.sock"
        if not os.path.exists(sock_path):
            return {}

        try:
            raw = _docker_get(sock_path, "/containers/json?all=1")
        except (OSError, ValueError):
            return {}

        import json

        try:
            containers = json.loads(raw)
        except (ValueError, TypeError):
            return {}

        names: dict[str, str] = {}
        for c in containers:
            cid = c.get("Id")
            name_list = c.get("Names") or []
            name = name_list[0].lstrip("/") if name_list else None
            if cid and name:
                names[cid] = name
                names[cid[:12]] = name
        return names

    def _is_included(self, proto: str, status: str) -> bool:
        """Mirror PsutilNetInfo: filter TCP by allowed_statuses; keep all UDP."""
        return not (
            proto == "tcp"
            and self.allowed_statuses is not None
            and status not in self.allowed_statuses
        )


def _docker_get(sock_path: str, path: str) -> str:
    """Minimal HTTP/1.0 GET over the Docker Unix socket; returns the JSON body."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    try:
        sock.connect(sock_path)
        request = (
            f"GET {path} HTTP/1.0\r\n"
            "Host: localhost\r\n"
            "Accept: application/json\r\n"
            "\r\n"
        )
        sock.sendall(request.encode("ascii"))

        chunks: list[bytes] = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        sock.close()

    data = b"".join(chunks)
    header, _, body = data.partition(b"\r\n\r\n")
    status_line = header.split(b"\r\n", 1)[0]
    if b" 200 " not in status_line:
        raise ValueError(f"docker socket returned: {status_line!r}")
    return body.decode("utf-8", errors="replace")
