"""Test the AppInfo facade: backend selection, cache, deferred verification, and enrichment."""

from __future__ import annotations

import os
import platform
import threading
from pathlib import Path

import pytest

from tapmap.model.appinfo import AppInfo, VerificationStatus
from tapmap.model.appinfo.app_info import ApplicationMetadata, _get_creator

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


# --- Background verification: fake backend, deferred/in-flight/dedupe behavior ---
#
# A fake AppInfoBackend is installed by monkeypatching AppInfo._select_backend,
# so these tests exercise the real locking/in-flight/executor machinery in
# AppInfo without depending on any real platform backend.


class _FakeBackend:
    """Controllable AppInfoBackend: defers verification unless told not to."""

    def __init__(self, *, defer: bool = True, block: threading.Event | None = None) -> None:
        self.defer = defer
        self.block = block
        self.identity_calls: list[str] = []
        self.verification_calls: list[str] = []
        self.fail_verification = False

    def resolve_identity(self, exe_path: str) -> ApplicationMetadata:
        self.identity_calls.append(exe_path)
        name = os.path.splitext(os.path.basename(exe_path))[0]
        return ApplicationMetadata(
            name=name,
            creator="Some Vendor" if not self.defer else None,
            verification_status=None if self.defer else VerificationStatus.VERIFIED,
            signature_state=None,
            signature_state_details=None,
        )

    def resolve_verification(
        self, exe_path: str, identity: ApplicationMetadata
    ) -> ApplicationMetadata:
        self.verification_calls.append(exe_path)
        if self.block is not None:
            self.block.wait(timeout=5)
        if self.fail_verification:
            raise RuntimeError("boom")
        return ApplicationMetadata(
            name=identity.name,
            creator="Some Vendor",
            verification_status=VerificationStatus.VERIFIED,
            signature_state="Signed",
            signature_state_details=None,
        )


def _install_fake_backend(monkeypatch: pytest.MonkeyPatch, backend: _FakeBackend) -> None:
    monkeypatch.setattr(AppInfo, "_select_backend", lambda self, path: backend)


def test_lookup_defers_and_returns_pending_immediately(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A first-sight lookup returns immediately with verification_status None."""
    backend = _FakeBackend(defer=True)
    _install_fake_backend(monkeypatch, backend)
    app_info = AppInfo(tmp_path)

    pending = app_info.lookup("/apps/foo.exe")

    assert pending.name == "foo"
    assert pending.verification_status is None
    assert backend.identity_calls == ["/apps/foo.exe"]

    app_info._executor.shutdown(wait=True)  # type: ignore[union-attr]


def test_lookup_resolves_once_background_verification_completes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A later lookup for the same exe sees the resolved result once the job finishes."""
    backend = _FakeBackend(defer=True)
    _install_fake_backend(monkeypatch, backend)
    app_info = AppInfo(tmp_path)

    app_info.lookup("/apps/foo.exe")
    app_info._executor.shutdown(wait=True)  # type: ignore[union-attr]

    resolved = app_info.lookup("/apps/foo.exe")

    assert resolved.verification_status == VerificationStatus.VERIFIED
    assert resolved.signature_state == "Signed"
    assert backend.verification_calls == ["/apps/foo.exe"]


def test_lookup_does_not_resubmit_while_verification_is_in_flight(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Repeated lookups for the same exe while verification is running do not resubmit."""
    block = threading.Event()
    backend = _FakeBackend(defer=True, block=block)
    _install_fake_backend(monkeypatch, backend)
    app_info = AppInfo(tmp_path)

    app_info.lookup("/apps/foo.exe")
    still_pending = app_info.lookup("/apps/foo.exe")
    app_info.lookup("/apps/foo.exe")

    assert still_pending.verification_status is None
    assert backend.identity_calls == ["/apps/foo.exe"]
    assert backend.verification_calls == ["/apps/foo.exe"]

    block.set()
    app_info._executor.shutdown(wait=True)  # type: ignore[union-attr]

    assert backend.verification_calls == ["/apps/foo.exe"]


def test_lookup_dedupes_concurrent_threads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Several threads racing on one brand-new exe verify it exactly once."""
    backend = _FakeBackend(defer=True)
    _install_fake_backend(monkeypatch, backend)
    app_info = AppInfo(tmp_path)

    thread_count = 8
    barrier = threading.Barrier(thread_count)
    results: list[ApplicationMetadata] = []
    results_lock = threading.Lock()

    def worker() -> None:
        barrier.wait(timeout=5)
        result = app_info.lookup("/apps/foo.exe")
        with results_lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    app_info._executor.shutdown(wait=True)  # type: ignore[union-attr]

    assert len(results) == thread_count
    assert backend.verification_calls == ["/apps/foo.exe"]


def test_run_verification_failure_produces_terminal_unknown_and_logs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A raising resolve_verification produces a logged, terminal UNKNOWN result."""
    backend = _FakeBackend(defer=True)
    backend.fail_verification = True
    _install_fake_backend(monkeypatch, backend)
    app_info = AppInfo(tmp_path)

    with caplog.at_level("ERROR"):
        app_info.lookup("/apps/foo.exe")
        app_info._executor.shutdown(wait=True)  # type: ignore[union-attr]

    resolved = app_info.lookup("/apps/foo.exe")
    assert resolved.verification_status == VerificationStatus.UNKNOWN
    assert resolved.creator == "Unknown"
    assert "background verification failed" in caplog.text

    # Not stuck pending, and not resubmitted on a later lookup.
    assert backend.verification_calls == ["/apps/foo.exe"]


def test_resolved_for_returns_only_terminal_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """resolved_for() omits pending/unseen exe paths and never triggers new work."""
    block = threading.Event()
    backend = _FakeBackend(defer=True, block=block)
    _install_fake_backend(monkeypatch, backend)
    app_info = AppInfo(tmp_path)

    app_info.lookup("/apps/pending.exe")

    result = app_info.resolved_for(["/apps/pending.exe", "/apps/never_seen.exe"])

    assert result == {}
    assert backend.identity_calls == ["/apps/pending.exe"]  # resolved_for triggered nothing new

    block.set()
    app_info._executor.shutdown(wait=True)  # type: ignore[union-attr]

    result = app_info.resolved_for(["/apps/pending.exe", "/apps/never_seen.exe"])
    assert set(result) == {"/apps/pending.exe"}
    assert result["/apps/pending.exe"].verification_status == VerificationStatus.VERIFIED


def test_close_shuts_down_executor_without_blocking(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """close() returns promptly, and a later lookup doesn't crash."""
    block = threading.Event()
    backend = _FakeBackend(defer=True, block=block)
    _install_fake_backend(monkeypatch, backend)
    app_info = AppInfo(tmp_path)

    app_info.lookup("/apps/foo.exe")

    app_info.close()  # must not block waiting on the still-running job
    block.set()

    # A lookup after close() is handled gracefully (submission is dropped, not raised).
    app_info.lookup("/apps/bar.exe")


def test_enrich_flattens_pending_verification_status_as_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """enrich() flattens a still-pending verification_status as None, not a string."""
    backend = _FakeBackend(defer=True)
    _install_fake_backend(monkeypatch, backend)
    app_info = AppInfo(tmp_path)

    conns = [{"exe": "/apps/foo.exe"}]
    app_info.enrich(conns)

    conn = conns[0]
    assert conn["app_verification_status"] is None
    assert conn["app_name"] == "foo"

    app_info._executor.shutdown(wait=True)  # type: ignore[union-attr]
