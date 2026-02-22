from __future__ import annotations

import os
import re
import subprocess
from typing import Any
from .netinfo import ProcessInfo


_PROC_RE = re.compile(r'users:\(\("(?P<name>[^"]+)",pid=(?P<pid>\d+),fd=\d+\)\)')


class LinuxNetInfo:
    """Collect socket records via iproute2 ss and attach process metadata (Linux).

    Notes:
        - Process details for other users often require root or capabilities.
        - Missing remote endpoints are returned as None, matching psutil behavior.
    """

    def __init__(self, allowed_statuses: set[str] | None = None) -> None:
        self.allowed_statuses = allowed_statuses

    def get_data(self) -> list[dict[str, Any]]:
        """Return connection records with socket and process fields."""
        proc_cache: dict[int, ProcessInfo] = {}
        results: list[dict[str, Any]] = []

        for line in self._run_ss():
            parsed = self._parse_ss_line(line)
            if parsed is None:
                continue

            if not self._is_included(parsed["proto"], parsed["status"]):
                continue

            pid = parsed["pid"]
            proc = self._get_process_info(pid, proc_cache)

            results.append(
                {
                    "pid": pid,
                    "proto": parsed["proto"],
                    "status": parsed["status"],
                    "family": parsed["family"],
                    "type": parsed["type"],
                    "laddr_ip": parsed["laddr_ip"],
                    "laddr_port": parsed["laddr_port"],
                    "raddr_ip": parsed["raddr_ip"],
                    "raddr_port": parsed["raddr_port"],
                    "process_status": proc.status,
                    "process_label": proc.label,
                    "process_name": proc.name,
                    "exe": proc.exe,
                    "cmdline": proc.cmdline,
                }
            )

        return results

    def _is_included(self, proto: str, status: str) -> bool:
        if proto != "tcp":
            return True
        if self.allowed_statuses is None:
            return True
        return status in self.allowed_statuses

    @staticmethod
    def _run_ss() -> list[str]:
        """Run ss and return output lines (no header)."""
        cmd = ["ss", "-H", "-n", "-t", "-u", "-a", "-p"]
        cp = subprocess.run(cmd, capture_output=True, text=True, check=False)
        out = (cp.stdout or "").strip()
        return out.splitlines() if out else []

    def _parse_ss_line(self, line: str) -> dict[str, Any] | None:
        # ss columns:
        # Netid State Recv-Q Send-Q Local Address:Port Peer Address:Port Process
        parts = line.split(maxsplit=6)
        if len(parts) < 6:
            return None

        netid = parts[0].strip()
        state = parts[1].strip() if len(parts) > 1 else ""
        local = parts[4].strip()
        peer = parts[5].strip()
        proc_field = parts[6].strip() if len(parts) >= 7 else ""

        proto = "udp" if netid.startswith("udp") else "tcp"
        sock_type = "SOCK_DGRAM" if proto == "udp" else "SOCK_STREAM"
        status = self._normalize_status(state)

        l_ip, l_port = self._split_addr(local, role="local")
        r_ip, r_port = self._split_addr(peer, role="peer")

        family = self._infer_family(l_ip, r_ip)

        pid, _name_from_ss = self._parse_pid_and_name(proc_field)

        return {
            "pid": pid,
            "proto": proto,
            "status": status,
            "family": family,
            "type": sock_type,
            "laddr_ip": l_ip,
            "laddr_port": l_port,
            "raddr_ip": r_ip,
            "raddr_port": r_port,
        }

    @staticmethod
    def _parse_pid_and_name(proc_field: str) -> tuple[int | None, str | None]:
        m = _PROC_RE.search(proc_field or "")
        if not m:
            return None, None
        try:
            return int(m.group("pid")), m.group("name")
        except ValueError:
            return None, None

    @staticmethod
    def _parse_port(port_str: str | None) -> int | None:
        if not port_str:
            return None
        s = port_str.strip()
        if s in {"*", "-", ""}:
            return None
        try:
            return int(s)
        except ValueError:
            return None

    def _split_addr(self, addr: str, *, role: str) -> tuple[str | None, int | None]:
        """Split ss address field into (ip, port).

        role:
            local: map '*' ip to '0.0.0.0' when it appears as local bind
            peer: treat wildcard peers as missing (None)
        """
        s = (addr or "").strip()
        if not s or s in {"*", "*:*"}:
            return self._normalize_ip("*", role=role), None

        if s.endswith(":*"):
            ip_part = s[:-2].strip()
            ip = self._normalize_ip(ip_part, role=role)
            return ip, None

        if s.startswith("["):
            right = s.rfind("]:")
            if right != -1:
                ip = s[1:right].strip()
                port_str = s[right + 2 :].strip()
                return self._normalize_ip(ip, role=role), self._parse_port(port_str)

        if s.count(":") >= 2:
            i = s.rfind(":")
            ip = s[:i].strip()
            port_str = s[i + 1 :].strip()
            return self._normalize_ip(ip, role=role), self._parse_port(port_str)

        if ":" in s:
            ip, port_str = s.rsplit(":", 1)
            return self._normalize_ip(ip.strip(), role=role), self._parse_port(port_str.strip())

        return self._normalize_ip(s, role=role), None

    @staticmethod
    def _normalize_ip(ip: str | None, *, role: str) -> str | None:
        """Normalize ip string from ss.

        Rules:
            - Strip brackets if present.
            - Strip zone suffix like '%wlp2s0' for stability.
            - local: map '*' to '0.0.0.0'
            - peer: map wildcards to None
        """
        if not ip:
            return None

        s = ip.strip()

        if s.startswith("[") and "]" in s:
            s = s[1 : s.index("]")].strip()

        if "%" in s:
            s = s.split("%", 1)[0].strip()

        if role == "local":
            if s == "*":
                return "0.0.0.0"
            return s or None

        # peer role
        if s in {"*", "0.0.0.0", "::"}:
            return None
        return s or None

    @staticmethod
    def _normalize_status(state: str | None) -> str:
        """Normalize ss TCP state names to psutil-compatible values."""
        if not state:
            return "NONE"

        mapping = {
            "ESTAB": "ESTABLISHED",
            "SYN-SENT": "SYN_SENT",
            "SYN-RECV": "SYN_RECV",
            "FIN-WAIT-1": "FIN_WAIT1",
            "FIN-WAIT-2": "FIN_WAIT2",
            "TIME-WAIT": "TIME_WAIT",
            "CLOSE-WAIT": "CLOSE_WAIT",
            "LAST-ACK": "LAST_ACK",
        }

        return mapping.get(state, state)

    @staticmethod
    def _infer_family(l_ip: str | None, r_ip: str | None) -> str:
        if (l_ip and ":" in l_ip) or (r_ip and ":" in r_ip):
            return "AF_INET6"
        return "AF_INET"

    def _get_process_info(self, pid: int | None, cache: dict[int, ProcessInfo]) -> ProcessInfo:
        """Return process metadata for a PID using /proc."""
        if pid is None or pid <= 0:
            return ProcessInfo(status="No process", label="No process")

        cached = cache.get(pid)
        if cached is not None:
            return cached

        info = self._read_proc_info(pid)
        cache[pid] = info
        return info

    @staticmethod
    def _read_proc_info(pid: int) -> ProcessInfo:
        base = f"/proc/{pid}"
        if not os.path.exists(base):
            return ProcessInfo(status="No process", label="No process")

        access_denied = False

        def safe_read_text(path: str) -> str | None:
            nonlocal access_denied
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    return f.read()
            except PermissionError:
                access_denied = True
                return None
            except FileNotFoundError:
                return None
            except OSError:
                return None

        def safe_readlink(path: str) -> str | None:
            nonlocal access_denied
            try:
                return os.readlink(path)
            except PermissionError:
                access_denied = True
                return None
            except FileNotFoundError:
                return None
            except OSError:
                return None

        name = None
        comm = safe_read_text(f"{base}/comm")
        if comm:
            name = comm.strip() or None

        exe = safe_readlink(f"{base}/exe")

        cmdline: list[str] | None = None
        try:
            with open(f"{base}/cmdline", "rb") as f:
                raw = f.read()
            parts = [p.decode("utf-8", errors="replace") for p in raw.split(b"\x00") if p]
            cmdline = parts or None
        except PermissionError:
            access_denied = True
        except (FileNotFoundError, OSError):
            pass

        if isinstance(name, str) and name:
            return ProcessInfo(status="OK", label=name, name=name, exe=exe, cmdline=cmdline)

        if access_denied:
            return ProcessInfo(status="Access denied", label="Access denied")

        return ProcessInfo(status="Unavailable", label="Unavailable")