"""Test backend selection and delegation in netinfo facade."""

from tapmap.model.netinfo import NetInfo


def test_select_backend_windows_uses_psutil(monkeypatch) -> None:
    """Verify Windows selects psutil backend."""
    monkeypatch.setattr("platform.system", lambda: "Windows")

    from model.netinfo_psutil import PsutilNetInfo

    netinfo = NetInfo()

    assert isinstance(netinfo._backend, PsutilNetInfo)


def test_select_backend_linux_uses_psutil(monkeypatch) -> None:
    """Verify Linux selects psutil backend."""
    monkeypatch.setattr("platform.system", lambda: "Linux")

    from model.netinfo_psutil import PsutilNetInfo

    netinfo = NetInfo()

    assert isinstance(netinfo._backend, PsutilNetInfo)


def test_select_backend_macos_uses_lsof(monkeypatch) -> None:
    """Verify macOS selects lsof backend."""
    monkeypatch.setattr("platform.system", lambda: "Darwin")

    from model.netinfo_lsof import LsofNetInfo

    netinfo = NetInfo()

    assert isinstance(netinfo._backend, LsofNetInfo)


def test_select_backend_raises_for_unsupported_os(monkeypatch) -> None:
    """Verify unsupported OS raises error."""
    monkeypatch.setattr("platform.system", lambda: "UnsupportedOS")

    netinfo = NetInfo.__new__(NetInfo)

    try:
        netinfo._select_backend()
    except NotImplementedError as exc:
        assert "UnsupportedOS" in str(exc)
    else:
        raise AssertionError("Expected NotImplementedError")
