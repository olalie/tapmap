from __future__ import annotations

import shlex
import subprocess
from typing import Any

from .netinfo import ProcessInfo


class LsofNetInfo:
    """Collect socket records via lsof and attach process metadata (macOS)."""

    def __init__(self, allowed_statuses: set[str] | None = None) -> None:
        self.allowed_statuses = allowed_statuses

    def get_data(self) -> list[dict[str, Any]]:
        """Return connection records with socket and process fields."""
        try:
            result = subprocess.run(
                ["lsof", "-nP", "+c", "0", "-i"],
                capture_output=True,
                text=True,
                check=True,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            return []

        lines = result.stdout.splitlines()
        if not lines:
            return []

        proc_cache: dict[int, ProcessInfo] = {}
        results: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()

        for line in lines[1:]:
            parts = line.split()
            if len(parts) < 9:
                continue

            command = self._decode_lsof_text(parts[0])
            pid = self._safe_int(parts[1])
            family = self._socket_family(parts[4])
            proto = parts[7].lower()
            socket_type = self._socket_type(proto)
            name_field = " ".join(parts[8:])

            l_ip, l_port, r_ip, r_port, status = self._parse_name(
                name_field,
                family=family,
            )

            if l_port is None:
                continue

            if not self._is_included(proto, status):
                continue

            proc = self._process_info(pid, command, proc_cache)

            key = (proto, status, family, l_ip, l_port, r_ip, r_port, pid)
            if key in seen:
                continue
            seen.add(key)

            results.append(
                {
                    "pid": pid,
                    "proto": proto,
                    "status": status,
                    "family": family,
                    "type": socket_type,
                    "laddr_ip": l_ip,
                    "laddr_port": l_port,
                    "raddr_ip": r_ip,
                    "raddr_port": r_port,
                    "process_status": proc.status,
                    "process_label": proc.label,
                    "process_name": proc.name,
                    "exe": proc.exe,
                    "cmdline": proc.cmdline,
                }
            )

        return results

    def _is_included(self, proto: str, status: str) -> bool:
        """Return True if the connection is included in the snapshot."""
        return not (
            proto == "tcp"
            and self.allowed_statuses is not None
            and status not in self.allowed_statuses
        )

    def _process_info(
        self,
        pid: int | None,
        command: str,
        cache: dict[int, ProcessInfo],
    ) -> ProcessInfo:
        """Return process metadata for a PID."""
        if pid is None or pid <= 0:
            return ProcessInfo(status="No process", label="System")

        cached = cache.get(pid)
        if cached is not None:
            return cached

        comm = self._read_ps_field(pid, "comm=")
        args = self._read_ps_field(pid, "args=")

        if comm is None and args is None:
            info = self._fallback_process_info(command)
            cache[pid] = info
            return info

        exe = comm or None
        cmdline = self._parse_cmdline(args, exe)

        if command:
            label = command
            name = command
        elif exe:
            label = exe.rsplit("/", 1)[-1]
            name = label
        else:
            info = ProcessInfo(status="Unavailable", label="Unavailable")
            cache[pid] = info
            return info

        info = ProcessInfo(
            status="OK",
            label=label,
            name=name,
            exe=exe,
            cmdline=cmdline,
        )
        cache[pid] = info
        return info

    @staticmethod
    def _fallback_process_info(command: str) -> ProcessInfo:
        """Return fallback process metadata from lsof command text."""
        if command:
            return ProcessInfo(
                status="OK",
                label=command,
                name=command,
                exe=None,
                cmdline=None,
            )
        return ProcessInfo(status="Unavailable", label="Unavailable")

    @staticmethod
    def _read_ps_field(pid: int, field: str) -> str | None:
        """Return one ps field for a PID."""
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", field],
                capture_output=True,
                text=True,
                check=True,
            )
        except (subprocess.SubprocessError, FileNotFoundError):
            return None

        value = result.stdout.strip()
        return value or None

    @staticmethod
    def _parse_cmdline(args: str | None, exe: str | None) -> list[str] | None:
        """Return command line arguments from ps output."""
        if args:
            try:
                return shlex.split(args)
            except ValueError:
                return [args]
        if exe:
            return [exe]
        return None

    @staticmethod
    def _socket_family(value: str) -> str | None:
        """Map lsof TYPE to OS address family code (psutil-compatible)."""
        if value == "IPv4":
            return "2"  # AF_INET
        if value == "IPv6":
            return "30"  # AF_INET6 on macOS
        return None

    @staticmethod
    def _socket_type(proto: str) -> str | None:
        """Return psutil-like socket type code from protocol."""
        if proto == "tcp":
            return "1"
        if proto == "udp":
            return "2"
        return None

    @staticmethod
    def _parse_name(
        name: str,
        *,
        family: str | None,
    ) -> tuple[str | None, int | None, str | None, int | None, str]:
        """Parse lsof NAME column into addresses and status."""
        status = "NONE"

        if "(" in name and ")" in name:
            status_text = name.split("(")[-1].split(")")[0].strip().upper()
            status = status_text.replace("-", "_")
            name = name.split("(")[0].strip()

        if "->" in name:
            left, right = name.split("->", 1)
            l_ip, l_port = LsofNetInfo._split_ip_port(left, family=family)
            r_ip, r_port = LsofNetInfo._split_ip_port(right, family=family)
            return l_ip, l_port, r_ip, r_port, status

        l_ip, l_port = LsofNetInfo._split_ip_port(name, family=family)
        return l_ip, l_port, None, None, status

    @staticmethod
    def _split_ip_port(
        value: str,
        *,
        family: str | None,
    ) -> tuple[str | None, int | None]:
        """Return normalized IP and port from lsof address text."""
        if not value:
            return None, None

        if value.startswith("["):
            end = value.find("]")
            if end == -1:
                ip = LsofNetInfo._normalize_ip(value, family=family)
                return ip, None

            ip = LsofNetInfo._normalize_ip(value[1:end], family=family)
            remainder = value[end + 1 :]
            if remainder.startswith(":"):
                try:
                    return ip, int(remainder[1:])
                except ValueError:
                    return ip, None
            return ip, None

        if ":" not in value:
            ip = LsofNetInfo._normalize_ip(value, family=family)
            return ip, None

        ip, port = value.rsplit(":", 1)
        ip = LsofNetInfo._normalize_ip(ip, family=family)
        try:
            return ip, int(port)
        except ValueError:
            return ip, None

    @staticmethod
    def _normalize_ip(value: str | None, *, family: str | None) -> str | None:
        """Return normalized IP text."""
        if value is None:
            return None
        if value == "*":
            if family == "10":
                return "::"
            return "0.0.0.0"
        return value

    @staticmethod
    def _safe_int(value: str) -> int | None:
        """Convert to int if possible."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _decode_lsof_text(value: str) -> str:
        """Return decoded text from lsof output."""
        if not value:
            return value
        try:
            return bytes(value, "utf-8").decode("unicode_escape")
        except UnicodeDecodeError:
            return value
