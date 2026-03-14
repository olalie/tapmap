"""Tests for Linux socket backend behavior."""

from model.netinfo_linux import LinuxNetInfo


def test_run_ss_returns_empty_when_ss_is_missing(monkeypatch) -> None:
    """Do not raise when iproute2 ss binary is unavailable."""

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("ss")

    monkeypatch.setattr("model.netinfo_linux.subprocess.run", fake_run)

    backend = LinuxNetInfo()

    assert backend.get_data() == []
