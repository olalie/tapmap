"""Test UnmappedState's per-service cache merge, retention, and AppInfo backfill."""

from __future__ import annotations

from typing import Any

from tapmap.state.service_entries import UNKNOWN_APP_KEY
from tapmap.state.unmapped_state import UnmappedState

_APP_FIELDS = (
    "app_name",
    "app_creator",
    "app_verification_status",
    "app_signature_state",
    "app_signature_state_details",
)

_DEFAULT_EXE = "/opt/app/app.exe"


def _candidate(**overrides: Any) -> dict[str, Any]:
    """Return a minimal unmapped PUBLIC candidate (as classified by ConnectionAnalyzer)."""
    candidate = {
        "ip": "203.0.113.7",
        "port": 8443,
        "proto": "tcp",
        "service": "https",
        "process_name": None,
        "pid": None,
        "exe": _DEFAULT_EXE,
        "app_name": None,
        "app_creator": None,
        "app_verification_status": None,
        "app_signature_state": None,
        "app_signature_state_details": None,
    }
    candidate.update(overrides)
    return candidate


def _app_fields(app: dict[str, Any]) -> dict[str, Any]:
    """Return only the app_* fields from an application record."""
    return {field: app.get(field) for field in _APP_FIELDS}


# --- merge: identity, deduplication, and field content ---


def test_merge_creates_entry_keyed_by_ip_port() -> None:
    """A new candidate creates one entry keyed by ip|port."""
    state = UnmappedState()

    cache = state.merge([_candidate()])

    assert "203.0.113.7|8443" in cache


def test_merge_deduplicates_repeated_observations_of_the_same_service() -> None:
    """Repeated merges of the same (ip, port) accumulate into one entry, not several."""
    state = UnmappedState()

    state.merge([_candidate()])
    cache = state.merge([_candidate()])

    assert len(cache) == 1


def test_merge_contains_no_geoip_fields() -> None:
    """An UnmappedState entry never carries mapped-only GeoIP fields."""
    state = UnmappedState()

    cache = state.merge([_candidate()])
    entry = cache["203.0.113.7|8443"]

    for field in ("lat", "lon", "city", "country", "country_code", "asn", "asn_org"):
        assert field not in entry


def test_merge_stores_service_field() -> None:
    """The port-service label is retained, since the technical view needs it."""
    state = UnmappedState()

    cache = state.merge([_candidate(service="https")])

    assert cache["203.0.113.7|8443"]["service"] == "https"


def test_merge_propagates_app_fields_into_new_application() -> None:
    """A new application record carries all five app_* fields from the candidate."""
    state = UnmappedState()

    candidate = _candidate(
        app_name="Firefox",
        app_creator="Mozilla Corporation",
        app_verification_status="verified",
        app_signature_state="SignedAndTrusted",
        app_signature_state_details="None",
    )

    cache = state.merge([candidate])
    app = cache["203.0.113.7|8443"]["applications"][_DEFAULT_EXE]

    assert _app_fields(app) == {
        "app_name": "Firefox",
        "app_creator": "Mozilla Corporation",
        "app_verification_status": "verified",
        "app_signature_state": "SignedAndTrusted",
        "app_signature_state_details": "None",
    }


def test_merge_uses_unknown_bucket_when_exe_missing() -> None:
    """Candidates with no resolvable exe path share a dedicated unknown-application bucket."""
    state = UnmappedState()

    cache = state.merge([_candidate(exe=None, process_name="svchost.exe", pid=100)])
    applications = cache["203.0.113.7|8443"]["applications"]

    assert UNKNOWN_APP_KEY in applications
    assert applications[UNKNOWN_APP_KEY]["processes"] == ["svchost.exe"]


def test_merge_accumulates_distinct_pids_for_the_same_process() -> None:
    """Multiple PIDs of the same process name accumulate under that application's record."""
    state = UnmappedState()

    cache = state.merge(
        [
            _candidate(process_name="firefox.exe", pid=4821),
            _candidate(process_name="firefox.exe", pid=5190),
        ]
    )
    app = cache["203.0.113.7|8443"]["applications"][_DEFAULT_EXE]

    assert app["proc_pids"] == {"firefox.exe": [4821, 5190]}


def test_merge_drops_candidate_with_invalid_port() -> None:
    """A candidate with a missing or non-numeric port is dropped, not stored under a -1 key."""
    state = UnmappedState()

    cache = state.merge([_candidate(port=None), _candidate(exe="/other.exe", port="not-a-port")])

    assert cache == {}


# --- clear: reset behavior ---


def test_clear_empties_the_cache() -> None:
    """clear() drops all accumulated entries and returns the new empty cache."""
    state = UnmappedState()
    state.merge([_candidate()])

    cache = state.clear()

    assert cache == {}
    assert state.cache == {}


# --- retention: pruning stale entries ---


def test_merge_prunes_entries_past_retention_window() -> None:
    """An entry whose last_seen predates the retention cutoff is dropped on the next merge."""
    state = UnmappedState(cache_retention_min=5)
    cache = state.merge([_candidate()])
    cache["203.0.113.7|8443"]["last_seen"] -= 10 * 60

    cache = state.merge([])

    assert cache == {}


def test_merge_keeps_entries_when_retention_disabled() -> None:
    """cache_retention_min=0 (the default) disables pruning entirely."""
    state = UnmappedState(cache_retention_min=0)
    cache = state.merge([_candidate()])
    cache["203.0.113.7|8443"]["last_seen"] -= 10_000 * 60

    cache = state.merge([])

    assert "203.0.113.7|8443" in cache


# --- pending verification: AppInfo backfill ---


def test_refresh_resolved_applications_updates_entry_whose_connection_has_vanished() -> None:
    """A retained cache entry whose connection has vanished still gets updated."""
    state = UnmappedState()

    # Tick 1: connection present, exe not yet verified.
    state.merge([_candidate(exe="/opt/app.exe", app_name="Firefox")])
    assert state.pending_exe_paths() == {"/opt/app.exe"}

    # Tick 2: connection is gone from the snapshot entirely.
    cache = state.merge([])
    assert "/opt/app.exe" in cache["203.0.113.7|8443"]["applications"]
    assert state.pending_exe_paths() == {"/opt/app.exe"}

    state.refresh_resolved_applications(
        {
            "/opt/app.exe": {
                "app_creator": "Mozilla Corporation",
                "app_verification_status": "verified",
                "app_signature_state": "SignedAndTrusted",
                "app_signature_state_details": None,
            }
        }
    )

    app = state.cache["203.0.113.7|8443"]["applications"]["/opt/app.exe"]
    assert app["app_verification_status"] == "verified"
    assert app["app_creator"] == "Mozilla Corporation"
    assert state.pending_exe_paths() == set()
