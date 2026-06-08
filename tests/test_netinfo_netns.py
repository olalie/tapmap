"""Tests for the cross-namespace backend's parsing and labeling."""
from __future__ import annotations

import pytest

from tapmap.model.netinfo_netns import _TCP_STATES, NetNsNetInfo


def _backend(allowed=None):
    return NetNsNetInfo(allowed_statuses=allowed)


# -- address parsing --------------------------------------------------------


def test_parse_ipv4_address_little_endian():
    # 0100007F:1F90 -> 127.0.0.1:8080 (bytes stored little-endian)
    ip, port = _backend()._parse_addr("0100007F:1F90", "IPv4")
    assert ip == "127.0.0.1"
    assert port == 8080


def test_parse_ipv4_remote():
    # 52438352 little-endian -> 82.131.67.... actually decode generically.
    ip, port = _backend()._parse_addr("0F02000A:01BB", "IPv4")
    assert ip == "10.0.2.15"
    assert port == 443


def test_parse_unbound_returns_none():
    ip, port = _backend()._parse_addr("00000000:0000", "IPv4")
    assert ip is None
    assert port is None


def test_parse_ipv6():
    # loopback ::1 in /proc form, port 0x1F90.
    token = "00000000000000000000000001000000:1F90"
    ip, port = _backend()._parse_addr(token, "IPv6")
    assert ip == "::1"
    assert port == 8080


# -- line parsing -----------------------------------------------------------


def test_parse_line_established_ipv4():
    line = "  1: 0F02000A:E4D2 12345678:01BB 01 00000000:00000000 00:00000000 00000000  1000 0 99 1 0"
    rec = _backend()._parse_line(line, proto="tcp", family="IPv4", sock_type="1")
    assert rec["status"] == "ESTABLISHED"
    assert rec["proto"] == "tcp"
    assert rec["family"] == "IPv4"
    assert rec["type"] == "1"
    assert rec["laddr_ip"] == "10.0.2.15"
    assert rec["raddr_port"] == 443
    assert rec["process_status"] == "OK"
    assert rec["exe"] is None and rec["cmdline"] is None


def test_parse_line_listen_has_no_remote():
    line = "  0: 0100007F:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000 1000 0 1 1 0"
    rec = _backend()._parse_line(line, proto="tcp", family="IPv4", sock_type="1")
    assert rec["status"] == "LISTEN"
    assert rec["raddr_ip"] is None
    assert rec["raddr_port"] is None


def test_udp_status_is_none():
    line = "  0: 0100007F:1F90 0F02000A:01BB 01 00000000:00000000 00:00000000 00000000 1000 0 1 1 0"
    rec = _backend()._parse_line(line, proto="udp", family="IPv4", sock_type="2")
    assert rec["status"] == "NONE"
    assert rec["type"] == "2"


def test_ipv4_mapped_demapped_to_ipv4():
    # ::ffff:217.131.67.82 in /proc tcp6 form. 0xD9834352 == 217.131.67.82.
    token = "0000000000000000FFFF00005243 83D9".replace(" ", "")
    token = token + ":01BB"
    line = f"  3: 00000000000000000000000000000000:E4D2 {token} 01 0 0 0"
    rec = _backend()._parse_line(line, proto="tcp", family="IPv6", sock_type="1")
    assert rec["raddr_ip"] == "217.131.67.82"
    assert rec["family"] == "IPv4"
    assert rec["raddr_port"] == 443


# -- state table ------------------------------------------------------------


@pytest.mark.parametrize(
    "code,expected",
    [
        ("01", "ESTABLISHED"),
        ("0A", "LISTEN"),
        ("06", "TIME_WAIT"),
        ("08", "CLOSE_WAIT"),
    ],
)
def test_state_table(code, expected):
    assert _TCP_STATES[code] == expected


def test_unknown_state_falls_back_to_none():
    line = "  0: 0100007F:1F90 0F02000A:01BB FF 0 0 0"
    rec = _backend()._parse_line(line, proto="tcp", family="IPv4", sock_type="1")
    assert rec["status"] == "NONE"


# -- allowed_statuses filter ------------------------------------------------


def test_allowed_statuses_filters_tcp():
    b = _backend(allowed={"ESTABLISHED"})
    assert b._is_included("tcp", "LISTEN") is False
    assert b._is_included("tcp", "ESTABLISHED") is True
    # UDP always kept regardless of filter.
    assert b._is_included("udp", "NONE") is True


# -- container labeling -----------------------------------------------------


def test_label_resolves_friendly_name():
    b = _backend()
    names = {"5c543658a54d": "jellyfin"}
    b._container_id = lambda pid: "5c543658a54dd9eb5651fcf71e160a00795a50c846b5"  # noqa: ARG005
    label = b._label_for(412095, names, inode=4026531999)
    assert label == "jellyfin"


def test_label_falls_back_to_short_id_when_name_unknown():
    b = _backend()
    b._container_id = lambda pid: "abcdef0123456789" + "0" * 48  # noqa: ARG005
    label = b._label_for(1, {}, inode=4026531999)
    assert label == "docker:abcdef012345"


def test_label_falls_back_to_netns_for_non_docker():
    b = _backend()
    b._container_id = lambda pid: None  # noqa: ARG005
    label = b._label_for(1, {}, inode=4026531999)
    assert label == "netns:4026531999"


def test_container_id_parses_cgroup(tmp_path, monkeypatch):
    cid = "5c543658a54dd9eb5651fcf71e160a00795a50c846b5101c6e4156dcdbf107b9"
    proc = tmp_path / "proc" / "412095"
    proc.mkdir(parents=True)
    (proc / "cgroup").write_text(f"0::/system.slice/docker-{cid}.scope\n")
    monkeypatch.chdir(tmp_path)

    # Point the open() at our fake tree via a tiny wrapper.
    import builtins

    real_open = builtins.open

    def fake_open(path, *a, **k):
        if str(path) == "/proc/412095/cgroup":
            return real_open(proc / "cgroup", *a, **k)
        return real_open(path, *a, **k)

    monkeypatch.setattr(builtins, "open", fake_open)
    assert NetNsNetInfo._container_id(412095) == cid[:64]


# -- graceful degradation ---------------------------------------------------


def test_get_data_returns_host_only_on_scan_error(monkeypatch):
    b = _backend()
    monkeypatch.setattr(b._host, "get_data", lambda: [{"pid": 1, "proto": "tcp"}])

    def boom():
        raise RuntimeError("no /proc")

    monkeypatch.setattr(b, "_collect_container_records", boom)
    assert b.get_data() == [{"pid": 1, "proto": "tcp"}]
