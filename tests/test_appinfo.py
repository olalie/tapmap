"""Test the AppInfo facade: backend selection, cache, enrichment, and creator resolution."""

from __future__ import annotations

import platform
from pathlib import Path

import pytest

from tapmap.model.appinfo import AppInfo, VerificationStatus
from tapmap.model.appinfo.app_info import _get_creator

# --- _get_creator: platform-independent creator resolution ---


def test_get_creator_prefers_company_name() -> None:
    """CompanyName wins over publisher."""
    assert _get_creator("Contoso Ltd", "Some Signer") == "Contoso Ltd"


def test_get_creator_falls_back_to_publisher() -> None:
    """Publisher is used when CompanyName is absent."""
    assert _get_creator(None, "Some Signer") == "Some Signer"


def test_get_creator_falls_back_to_unknown() -> None:
    """Unknown is returned when neither CompanyName nor publisher is available."""
    assert _get_creator(None, None) == "Unknown"


# --- backend selection ---
#
# Only the non-Windows / disabled paths are exercised here. A test that
# constructs a real WindowsAppInfoBackend against the actual wrapper DLL was
# considered and rejected: loading it is a real, process-wide, one-time side
# effect (see windows_signature_info.load()) that would leak into later
# tests in the same process, since it can't be undone. That path is already
# covered by manual verification against the real DLL, not automated here.


def test_select_backend_returns_none_on_unsupported_os(monkeypatch, tmp_path: Path) -> None:
    """No backend is selected on an OS with no implementation."""
    monkeypatch.setattr("platform.system", lambda: "FreeBSD")

    app_info = AppInfo(tmp_path)

    assert app_info._backend is None
    assert app_info.enabled is False


# --- AppInfo: disabled mode (no backend available) ---


def test_disabled_when_dll_missing(monkeypatch, tmp_path: Path) -> None:
    """AppInfo reports disabled when the Windows backend cannot be constructed."""
    monkeypatch.setattr("platform.system", lambda: "Windows")

    app_info = AppInfo(tmp_path / "does_not_exist")
    assert app_info.enabled is False


def test_lookup_disabled_falls_back_to_filename_metadata(monkeypatch, tmp_path: Path) -> None:
    """Disabled AppInfo still resolves a usable name/creator/verification_status from the path."""
    monkeypatch.setattr("platform.system", lambda: "FreeBSD")
    app_info = AppInfo(tmp_path / "does_not_exist")

    metadata = app_info.lookup("/apps/foo.exe")

    assert metadata.name == "foo"
    assert metadata.creator == "Unknown"
    assert metadata.verification_status == VerificationStatus.UNKNOWN
    assert metadata.signature_state is None
    assert metadata.signature_state_details is None


@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="exercises os.path.normcase's case-insensitive behavior, which is Windows-specific",
)
def test_lookup_caches_by_normalized_path(tmp_path: Path) -> None:
    """Repeated lookups for the same path (any case) return the cached object."""
    app_info = AppInfo(tmp_path / "does_not_exist")

    first = app_info.lookup(r"C:\Apps\Foo.exe")
    second = app_info.lookup(r"C:\Apps\Foo.exe")
    third = app_info.lookup(r"C:\APPS\FOO.EXE")

    assert first is second
    assert first is third


def test_cache_size_zero_disables_caching(tmp_path: Path) -> None:
    """cache_size=0 recomputes on every lookup instead of caching."""
    app_info = AppInfo(tmp_path / "does_not_exist", cache_size=0)

    first = app_info.lookup(r"C:\Apps\Foo.exe")
    second = app_info.lookup(r"C:\Apps\Foo.exe")

    assert first == second
    assert first is not second


def test_lru_eviction_drops_least_recently_used(tmp_path: Path) -> None:
    """The oldest entry is evicted once the cache exceeds its size."""
    app_info = AppInfo(tmp_path / "does_not_exist", cache_size=1)

    first = app_info.lookup(r"C:\Apps\Foo.exe")
    app_info.lookup(r"C:\Apps\Bar.exe")
    first_again = app_info.lookup(r"C:\Apps\Foo.exe")

    assert first == first_again
    assert first is not first_again


def test_enrich_returns_non_list_unchanged(tmp_path: Path) -> None:
    """enrich() is a no-op for non-list or empty input."""
    app_info = AppInfo(tmp_path / "does_not_exist")

    assert app_info.enrich(None) is None  # type: ignore[arg-type]
    assert app_info.enrich([]) == []


def test_enrich_skips_connections_without_exe(tmp_path: Path) -> None:
    """Connections with no exe path are left unenriched."""
    app_info = AppInfo(tmp_path / "does_not_exist")

    conns = [{"exe": None}, {"exe": ""}, {"pid": 1}]
    app_info.enrich(conns)

    for conn in conns:
        assert "app_name" not in conn


def test_enrich_flattens_metadata_into_connections(monkeypatch, tmp_path: Path) -> None:
    """enrich() flattens ApplicationMetadata onto each connection dict as plain strings."""
    monkeypatch.setattr("platform.system", lambda: "FreeBSD")
    app_info = AppInfo(tmp_path / "does_not_exist")

    conns = [{"exe": "/Apps/Foo.exe"}]
    app_info.enrich(conns)

    conn = conns[0]
    assert conn["app_name"] == "Foo"
    assert conn["app_creator"] == "Unknown"
    assert conn["app_verification_status"] == "unknown"
    assert isinstance(conn["app_verification_status"], str)
    assert conn["app_signature_state"] is None
    assert conn["app_signature_state_details"] is None
