"""Test normalization of psutil network connections."""
import socket
from types import SimpleNamespace

import psutil

from tapmap.model.netinfo_psutil import PsutilNetInfo


class FakeProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid

    def name(self) -> str:
        return "app.exe"

    def exe(self) -> str:
        return r"C:\Program Files\App\app.exe"

    def cmdline(self) -> list[str]:
        return [r"C:\Program Files\App\app.exe", "--flag"]


def test_psutil_normalizes_tcp_listen_ipv4(monkeypatch) -> None:
    """Verify IPv4 connection is normalized correctly."""
    raw_conn = SimpleNamespace(
        pid=1001,
        status="LISTEN",
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
        laddr=SimpleNamespace(ip="127.0.0.1", port=8080),
        raddr=(),
    )

    def fake_net_connections(kind: str):
        if kind == "tcp":
            return [raw_conn]
        return []

    monkeypatch.setattr(psutil, "net_connections", fake_net_connections)
    monkeypatch.setattr(psutil, "Process", FakeProcess)

    data = PsutilNetInfo().get_data()

    assert data == [
        {
            "pid": 1001,
            "proto": "tcp",
            "status": "LISTEN",
            "family": "IPv4",
            "type": "1",
            "laddr_ip": "127.0.0.1",
            "laddr_port": 8080,
            "raddr_ip": None,
            "raddr_port": None,
            "process_status": "OK",
            "process_label": "app.exe",
            "process_name": "app.exe",
            "exe": r"C:\Program Files\App\app.exe",
            "cmdline": [r"C:\Program Files\App\app.exe", "--flag"],
        }
    ]


def test_psutil_normalizes_tcp_established_ipv6(monkeypatch) -> None:
    """Verify IPv6 connection is normalized correctly."""
    raw_conn = SimpleNamespace(
        pid=2002,
        status="ESTABLISHED",
        family=socket.AF_INET6,
        type=socket.SOCK_STREAM,
        laddr=SimpleNamespace(ip="2001:db8::10", port=55000),
        raddr=SimpleNamespace(ip="2001:db8::20", port=443),
    )

    def fake_net_connections(kind: str):
        if kind == "tcp":
            return [raw_conn]
        return []

    monkeypatch.setattr(psutil, "net_connections", fake_net_connections)
    monkeypatch.setattr(psutil, "Process", FakeProcess)

    data = PsutilNetInfo().get_data()

    assert data == [
        {
            "pid": 2002,
            "proto": "tcp",
            "status": "ESTABLISHED",
            "family": "IPv6",
            "type": "1",
            "laddr_ip": "2001:db8::10",
            "laddr_port": 55000,
            "raddr_ip": "2001:db8::20",
            "raddr_port": 443,
            "process_status": "OK",
            "process_label": "app.exe",
            "process_name": "app.exe",
            "exe": r"C:\Program Files\App\app.exe",
            "cmdline": [r"C:\Program Files\App\app.exe", "--flag"],
        }
    ]
