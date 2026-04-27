"""Test normalization of lsof network connections."""

from types import SimpleNamespace

from tapmap.model.netinfo_lsof import LsofNetInfo


def test_lsof_ipv4_and_ipv6_normalized(monkeypatch) -> None:
    """Verify IPv4 and IPv6 connections are normalized correctly."""
    lsof_output = """COMMAND   PID USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
ControlCenter 626 user 9u IPv4 0x0 0t0 TCP *:7000 (LISTEN)
rapportd 709 user 22u IPv4 0x0 0t0 TCP 192.168.1.10:49152->192.168.1.20:52916 (ESTABLISHED)
firefox 1070 user 31u IPv6 0x0 0t0 TCP [2a01::1]:49165->[2600::1]:80 (ESTABLISHED)
firefox 1070 user 176u IPv6 0x0 0t0 UDP *:52569
"""

    ps_data = {
        ("626", "comm="): "/System/ControlCenter",
        ("626", "args="): "/System/ControlCenter",
        ("709", "comm="): "/usr/libexec/rapportd",
        ("709", "args="): "/usr/libexec/rapportd",
        ("1070", "comm="): "/Applications/firefox",
        ("1070", "args="): "/Applications/firefox",
    }

    def fake_run(cmd, capture_output, text, check):
        if cmd[0] == "lsof":
            return SimpleNamespace(stdout=lsof_output)

        if cmd[0] == "ps":
            pid = cmd[2]
            field = cmd[4]
            value = ps_data.get((pid, field), "")
            return SimpleNamespace(stdout=value)

        raise ValueError(f"Unexpected command: {cmd}")

    monkeypatch.setattr("subprocess.run", fake_run)

    results = LsofNetInfo().get_data()

    assert len(results) == 4

    r = results[0]
    assert r["pid"] == 626
    assert r["proto"] == "tcp"
    assert r["status"] == "LISTEN"
    assert r["family"] == "IPv4"
    assert r["type"] == "1"
    assert r["laddr_ip"] == "0.0.0.0"
    assert r["laddr_port"] == 7000
    assert r["raddr_ip"] is None
    assert r["raddr_port"] is None
    assert r["process_status"] == "OK"
    assert r["process_label"] == "ControlCenter"
    assert r["process_name"] == "ControlCenter"
    assert r["exe"] == "/System/ControlCenter"
    assert r["cmdline"] == ["/System/ControlCenter"]

    r = results[1]
    assert r["pid"] == 709
    assert r["proto"] == "tcp"
    assert r["status"] == "ESTABLISHED"
    assert r["family"] == "IPv4"
    assert r["type"] == "1"
    assert r["laddr_ip"] == "192.168.1.10"
    assert r["laddr_port"] == 49152
    assert r["raddr_ip"] == "192.168.1.20"
    assert r["raddr_port"] == 52916
    assert r["process_status"] == "OK"
    assert r["process_label"] == "rapportd"
    assert r["process_name"] == "rapportd"
    assert r["exe"] == "/usr/libexec/rapportd"
    assert r["cmdline"] == ["/usr/libexec/rapportd"]

    r = results[2]
    assert r["pid"] == 1070
    assert r["proto"] == "tcp"
    assert r["status"] == "ESTABLISHED"
    assert r["family"] == "IPv6"
    assert r["type"] == "1"
    assert r["laddr_ip"] == "2a01::1"
    assert r["laddr_port"] == 49165
    assert r["raddr_ip"] == "2600::1"
    assert r["raddr_port"] == 80
    assert r["process_status"] == "OK"
    assert r["process_label"] == "firefox"
    assert r["process_name"] == "firefox"
    assert r["exe"] == "/Applications/firefox"
    assert r["cmdline"] == ["/Applications/firefox"]

    r = results[3]
    assert r["pid"] == 1070
    assert r["proto"] == "udp"
    assert r["status"] == "NONE"
    assert r["family"] == "IPv6"
    assert r["type"] == "2"
    assert r["laddr_ip"] == "::"
    assert r["laddr_port"] == 52569
    assert r["raddr_ip"] is None
    assert r["raddr_port"] is None
    assert r["process_status"] == "OK"
    assert r["process_label"] == "firefox"
    assert r["process_name"] == "firefox"
    assert r["exe"] == "/Applications/firefox"
    assert r["cmdline"] == ["/Applications/firefox"]
