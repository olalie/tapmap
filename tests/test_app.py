"""Test TapMap's coordination of ConnectionState and UnmappedState."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from tapmap.app import TapMap
from tapmap.model.appinfo import ApplicationMetadata, VerificationStatus
from tapmap.state.connection_state import ConnectionState
from tapmap.state.status_cache import StatusCache
from tapmap.state.unmapped_state import UnmappedState
from tapmap.ui.service_point_view import ServicePointViewBuilder


def _bare_app() -> TapMap:
    """Return a TapMap instance with only the attributes needed for method-level tests."""
    app = object.__new__(TapMap)
    app.connection_state = ConnectionState()
    app.unmapped_state = UnmappedState()
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


def test_refresh_pending_app_verifications_updates_both_states() -> None:
    """A resolved exe backfills matching entries in both ConnectionState and UnmappedState."""
    app = _bare_app()
    app.connection_state.merge([_mapped_candidate(exe="/opt/app.exe", app_name="Firefox")])
    app.unmapped_state.merge([_unmapped_candidate(exe="/opt/app.exe", app_name="Firefox")])

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

    assert mapped_app["app_verification_status"] == "verified"
    assert mapped_app["app_creator"] == "Mozilla Corporation"
    assert unmapped_app["app_verification_status"] == "verified"
    assert unmapped_app["app_creator"] == "Mozilla Corporation"
