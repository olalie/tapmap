"""Test TapMap's coordination of ConnectionState and UnmappedState."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from tapmap.app import APP_META, TapMap
from tapmap.model.appinfo import ApplicationMetadata, VerificationStatus
from tapmap.runtime import RuntimeContext
from tapmap.significant_connections_persistence import load_significant_connections
from tapmap.state.connection_state import ConnectionState
from tapmap.state.significant_connections import SignificantConnections
from tapmap.state.status_cache import StatusCache
from tapmap.state.unmapped_state import UnmappedState
from tapmap.ui.service_point_view import ServicePointViewBuilder


def _runtime_ctx(tmp_path: Path) -> RuntimeContext:
    """Build a minimal runtime context for app construction tests."""
    return RuntimeContext(
        meta=APP_META,
        app_data_dir=tmp_path,
        run_dir=tmp_path,
        is_frozen=False,
        net_backend="psutil",
        net_backend_version="test",
        server_host="127.0.0.1",
        server_port=8050,
        launch_browser=True,
        cache_retention_min=0,
        is_docker=False,
        location_override=None,
        security_extensions_dir=tmp_path,
        tray_icon_path=tmp_path / "tapmap.ico",
    )


def _bare_app() -> TapMap:
    """Return a TapMap instance with only the attributes needed for method-level tests."""
    app = object.__new__(TapMap)
    app.connection_state = ConnectionState()
    app.unmapped_state = UnmappedState()
    app.significant_connections = SignificantConnections([])
    app.view_builder = ServicePointViewBuilder(coord_precision=3, is_docker=False)
    app.model = SimpleNamespace(appinfo=MagicMock())
    app.MIN_FLASH_S = TapMap.MIN_FLASH_S
    return app


def _mapped_candidate(**overrides: object) -> dict[str, object]:
    """Return a minimal mapped PUBLIC candidate for ConnectionState.merge()."""
    candidate = {
        "ip": "8.8.8.8",
        "port": 443,
        "proto": "tcp",
        "process_name": None,
        "pid": None,
        "exe": "/opt/app.exe",
        "lon": 37.4,
        "lat": -122.1,
        "city": "Mountain View",
        "country": "United States",
        "country_code": "US",
        "asn": 15169,
        "asn_org": "Google LLC",
        "app_name": None,
        "app_creator": None,
        "app_verification_status": None,
        "app_signature_state": None,
        "app_signature_state_details": None,
    }
    candidate.update(overrides)
    return candidate


def _unmapped_candidate(**overrides: object) -> dict[str, object]:
    """Return a minimal unmapped PUBLIC candidate for UnmappedState.merge()."""
    candidate = {
        "ip": "203.0.113.7",
        "port": 8443,
        "proto": "tcp",
        "service": "https",
        "process_name": None,
        "pid": None,
        "exe": "/opt/app.exe",
        "app_name": None,
        "app_creator": None,
        "app_verification_status": None,
        "app_signature_state": None,
        "app_signature_state_details": None,
    }
    candidate.update(overrides)
    return candidate


# --- Clear cache ---


def test_handle_clear_cache_clears_both_connection_and_unmapped_state() -> None:
    """Clear cache empties both ConnectionState and UnmappedState, not just the mapped one."""
    app = _bare_app()
    app.connection_state.merge([_mapped_candidate()])
    app.unmapped_state.merge([_unmapped_candidate()])

    app._handle_clear_cache(StatusCache(), False)

    assert app.connection_state.cache == {}
    assert app.unmapped_state.cache == {}


# --- Deferred AppInfo verification ---


def _pending_significant_event(**overrides: object) -> dict[str, object]:
    """Return a minimal persisted Significant Connection event awaiting verification."""
    event = {
        "timestamp": "2026-08-23T18:42:16.013313",
        "reasons": ["new_app"],
        "pid": 4821,
        "proto": "tcp",
        "ip": "8.8.8.8",
        "port": 443,
        "service": "https",
        "lat": 37.4,
        "lon": -122.1,
        "process_name": "firefox.exe",
        "exe": "/opt/app.exe",
        "city": "Mountain View",
        "country": "United States",
        "country_code": "US",
        "asn": 15169,
        "asn_org": "Google LLC",
        "app_name": "Firefox",
        "app_creator": None,
        "app_verification_status": None,
        "app_signature_state": None,
        "app_signature_state_details": None,
    }
    event.update(overrides)
    return event


def test_refresh_pending_app_verifications_updates_all_three_states() -> None:
    """A resolved exe backfills all three states.

    Covers ConnectionState, UnmappedState, and SignificantConnections alike.
    """
    app = _bare_app()
    app.connection_state.merge([_mapped_candidate(exe="/opt/app.exe", app_name="Firefox")])
    app.unmapped_state.merge([_unmapped_candidate(exe="/opt/app.exe", app_name="Firefox")])
    app.significant_connections.add(_pending_significant_event())

    app.model.appinfo.resolved_for.return_value = {
        "/opt/app.exe": ApplicationMetadata(
            name="Firefox",
            creator="Mozilla Corporation",
            verification_status=VerificationStatus.VERIFIED,
            signature_state="SignedAndTrusted",
            signature_state_details=None,
        )
    }

    app._refresh_pending_app_verifications()

    mapped_app = app.connection_state.cache["8.8.8.8|443"]["applications"]["/opt/app.exe"]
    unmapped_app = app.unmapped_state.cache["203.0.113.7|8443"]["applications"]["/opt/app.exe"]
    significant_event = app.significant_connections.items[0]

    assert mapped_app["app_verification_status"] == "verified"
    assert mapped_app["app_creator"] == "Mozilla Corporation"
    assert unmapped_app["app_verification_status"] == "verified"
    assert unmapped_app["app_creator"] == "Mozilla Corporation"
    assert significant_event["app_verification_status"] == "verified"
    assert significant_event["app_creator"] == "Mozilla Corporation"
    assert significant_event["reasons"] == ["new_app"]


def test_refresh_pending_app_verifications_queries_significant_connections_only_pending_exe(
) -> None:
    """An exe pending only in SignificantConnections is still queried and backfilled.

    Covers an exe already evicted from the ConnectionState/UnmappedState live caches.
    """
    app = _bare_app()
    app.significant_connections.add(_pending_significant_event(exe="/opt/gone.exe"))

    app.model.appinfo.resolved_for.return_value = {
        "/opt/gone.exe": ApplicationMetadata(
            name="Firefox",
            creator="Mozilla Corporation",
            verification_status=VerificationStatus.FAILED,
            signature_state="Unsigned",
            signature_state_details=None,
        )
    }

    app._refresh_pending_app_verifications()

    app.model.appinfo.resolved_for.assert_called_once_with({"/opt/gone.exe"})
    assert app.significant_connections.items[0]["app_verification_status"] == "failed"


def test_refresh_pending_app_verifications_persists_the_corrected_significant_event(
    tmp_path: Path,
) -> None:
    """A Significant Connection backfilled in memory is saved to disk, not only in memory."""
    app = TapMap(_runtime_ctx(tmp_path))
    try:
        app.significant_connections.add(_pending_significant_event())

        resolved_metadata = ApplicationMetadata(
            name="Firefox",
            creator="Mozilla Corporation",
            verification_status=VerificationStatus.VERIFIED,
            signature_state="SignedAndTrusted",
            signature_state_details=None,
        )
        app.model.appinfo.resolved_for = lambda _paths: {"/opt/app.exe": resolved_metadata}

        app._refresh_pending_app_verifications()
        app._save_history()

        persisted = load_significant_connections(app.significant_connections_path)
        assert len(persisted) == 1
        assert persisted[0]["app_verification_status"] == "verified"
        assert persisted[0]["app_creator"] == "Mozilla Corporation"
        assert persisted[0]["reasons"] == ["new_app"]
    finally:
        app.close()
