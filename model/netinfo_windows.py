from __future__ import annotations

from collections.abc import Callable
from typing import Any

import psutil

from .netinfo import ProcessInfo


class WindowsNetInfo:
    """Collect socket records via psutil and attach process metadata (Windows)."""

    KINDS = ("tcp", "udp")

    def __init__(self, allowed_statuses: set[str] | None = None) -> None:
        self.allowed_statuses = allowed_statuses

    def get_data(self) -> list[dict[str, Any]]:
        """Return connection records with socket and process fields."""
        proc_cache: dict[int, ProcessInfo] = {}
        results: list[dict[str, Any]] = []

        for proto in self.KINDS:
            try:
                conns = psutil.net_connections(kind=proto)
            except (psutil.AccessDenied, PermissionError):
                continue
            except (OSError, RuntimeError):
                continue

            for conn in conns:
                if not self._is_included(conn, proto=proto):
                    continue

                pid = conn.pid
                proc = self._process_info(pid, proc_cache)

                l_ip, l_port = self._split_addr(conn.laddr)
                r_ip, r_port = self._split_addr(conn.raddr)

                results.append(
                    {
                        "pid": pid,
                        "proto": proto,
                        "status": conn.status or "NONE",
                        "family": str(conn.family).replace("AddressFamily.", ""),
                        "type": str(conn.type).replace("SocketKind.", ""),
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

    def _is_included(self, conn: Any, *, proto: str) -> bool:
        """Return True if the connection is included in the snapshot."""
        status = conn.status or "NONE"
        return not (
            proto == "tcp"
            and self.allowed_statuses is not None
            and status not in self.allowed_statuses
        )

    def _process_info(
        self,
        pid: int | None,
        cache: dict[int, ProcessInfo],
    ) -> ProcessInfo:
        """Return process metadata for a PID."""
        if pid is None or pid <= 0:
            return ProcessInfo(status="No process", label="No process")

        cached = cache.get(pid)
        if cached is not None:
            return cached

        try:
            proc = psutil.Process(pid)
        except psutil.NoSuchProcess:
            info = ProcessInfo(status="No process", label="No process")
            cache[pid] = info
            return info
        except psutil.AccessDenied:
            info = ProcessInfo(status="Access denied", label="Access denied")
            cache[pid] = info
            return info
        except (psutil.ZombieProcess, OSError, RuntimeError):
            info = ProcessInfo(status="Unavailable", label="Unavailable")
            cache[pid] = info
            return info

        access_denied = False

        def read(fn: Callable[[], Any]) -> Any:
            nonlocal access_denied
            try:
                return fn()
            except psutil.AccessDenied:
                access_denied = True
                return None
            except psutil.NoSuchProcess:
                return None
            except (OSError, RuntimeError):
                return None

        with proc.oneshot():
            name = read(proc.name)
            exe = read(proc.exe)
            cmdline = read(proc.cmdline)

        if isinstance(name, str) and name:
            info = ProcessInfo(
                status="OK",
                label=name,
                name=name,
                exe=exe,
                cmdline=cmdline,
            )
        elif access_denied:
            info = ProcessInfo(status="Access denied", label="Access denied")
        else:
            info = ProcessInfo(status="Unavailable", label="Unavailable")

        cache[pid] = info
        return info

    @staticmethod
    def _split_addr(addr: Any) -> tuple[str | None, int | None]:
        """Return (ip, port) from a psutil address value."""
        if not addr:
            return None, None
        try:
            return addr.ip, addr.port
        except AttributeError:
            return addr[0], addr[1]