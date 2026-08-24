"""Test ConnectionState's per-service cache merge, retention, and AppInfo backfill."""

from __future__ import annotations

from typing import Any

from tapmap.state.connection_state import ConnectionState
from tapmap.state.service_entries import UNKNOWN_APP_KEY

_APP_FIELDS = (
    "app_name",
    "app_creator",
    "app_verification_status",
    "app_signature_state",
    "app_signature_state_details",
)

_DEFAULT_EXE = "/opt/app/app.exe"


def _candidate(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid map candidate (as produced by Model.snapshot())."""
    candidate = {
        "ip": "8.8.8.8",
        "port": 443,
        "proto": "tcp",
        "process_name": None,
        "pid": None,
        "exe": _DEFAULT_EXE,
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


def _app_fields(app: dict[str, Any]) -> dict[str, Any]:
    """Return only the app_* fields from an application record."""
    return {field: app.get(field) for field in _APP_FIELDS}


# --- merge: application record propagation ---


def test_merge_propagates_app_fields_into_new_application() -> None:
    """A new application record carries all five app_* fields from the candidate."""
    state = ConnectionState()

    candidate = _candidate(
        app_name="Firefox",
        app_creator="Mozilla Corporation",
        app_verification_status="verified",
        app_signature_state="SignedAndTrusted",
        app_signature_state_details="None",
    )

    cache = state.merge([candidate])
    app = cache["8.8.8.8|443"]["applications"][_DEFAULT_EXE]

    assert _app_fields(app) == {
        "app_name": "Firefox",
        "app_creator": "Mozilla Corporation",
        "app_verification_status": "verified",
        "app_signature_state": "SignedAndTrusted",
        "app_signature_state_details": "None",
    }


def test_merge_leaves_app_fields_none_when_absent() -> None:
    """A candidate with no app data (AppInfo disabled) leaves app_* fields None."""
    state = ConnectionState()

    cache = state.merge([_candidate()])
    app = cache["8.8.8.8|443"]["applications"][_DEFAULT_EXE]

    assert _app_fields(app) == dict.fromkeys(_APP_FIELDS)


def test_merge_backfills_app_fields_on_existing_application() -> None:
    """A later candidate fills in app_* fields that were previously missing."""
    state = ConnectionState()

    state.merge([_candidate()])
    cache = state.merge(
        [
            _candidate(
                app_name="Firefox",
                app_creator="Mozilla Corporation",
                app_verification_status="verified",
                app_signature_state="SignedAndTrusted",
                app_signature_state_details="None",
            )
        ]
    )
    app = cache["8.8.8.8|443"]["applications"][_DEFAULT_EXE]

    assert app["app_name"] == "Firefox"
    assert app["app_verification_status"] == "verified"


def test_merge_keeps_first_app_value_for_same_exe() -> None:
    """A distinct later value for the same exe path does not overwrite the first."""
    state = ConnectionState()

    state.merge([_candidate(app_name="Firefox", app_verification_status="verified")])
    cache = state.merge([_candidate(app_name="Other Name", app_verification_status="failed")])
    app = cache["8.8.8.8|443"]["applications"][_DEFAULT_EXE]

    assert app["app_name"] == "Firefox"
    assert app["app_verification_status"] == "verified"


def test_merge_keeps_different_exe_paths_separate() -> None:
    """Two different applications sharing (ip, port) each get their own application record."""
    state = ConnectionState()

    cache = state.merge(
        [
            _candidate(
                exe="/opt/firefox/firefox.exe",
                app_name="Firefox",
                app_verification_status="verified",
            ),
            _candidate(
                exe="/tmp/malware.exe", app_name="Malware", app_verification_status="failed"
            ),
        ]
    )
    applications = cache["8.8.8.8|443"]["applications"]

    assert applications["/opt/firefox/firefox.exe"]["app_name"] == "Firefox"
    assert applications["/opt/firefox/firefox.exe"]["app_verification_status"] == "verified"
    assert applications["/tmp/malware.exe"]["app_name"] == "Malware"
    assert applications["/tmp/malware.exe"]["app_verification_status"] == "failed"


def test_merge_uses_unknown_bucket_when_exe_missing() -> None:
    """Candidates with no resolvable exe path share a dedicated unknown-application bucket."""
    state = ConnectionState()

    cache = state.merge([_candidate(exe=None, process_name="svchost.exe", pid=100)])
    applications = cache["8.8.8.8|443"]["applications"]

    assert UNKNOWN_APP_KEY in applications
    assert applications[UNKNOWN_APP_KEY]["processes"] == ["svchost.exe"]


def test_merge_accumulates_processes_within_application() -> None:
    """Multiple processes for the same exe path accumulate in that application's record."""
    state = ConnectionState()

    cache = state.merge(
        [
            _candidate(process_name="Spotify.exe", pid=17840),
            _candidate(process_name="SpotifyLauncher.exe", pid=16696),
        ]
    )
    app = cache["8.8.8.8|443"]["applications"][_DEFAULT_EXE]

    assert app["processes"] == ["Spotify.exe", "SpotifyLauncher.exe"]
    assert app["proc_pids"] == {"Spotify.exe": [17840], "SpotifyLauncher.exe": [16696]}


def test_merge_propagates_country_code() -> None:
    """country_code is propagated the same way as the other geo fields."""
    state = ConnectionState()

    cache = state.merge([_candidate(country_code="NO")])
    entry = cache["8.8.8.8|443"]

    assert entry["country_code"] == "NO"


def test_merge_drops_candidate_with_invalid_port() -> None:
    """A candidate with a missing or non-numeric port is dropped, not stored under a -1 key."""
    state = ConnectionState()

    cache = state.merge([_candidate(port=None), _candidate(exe="/other.exe", port="not-a-port")])

    assert cache == {}


# --- clear: reset behavior ---


def test_clear_empties_the_cache() -> None:
    """clear() drops all accumulated entries and returns the new empty cache."""
    state = ConnectionState()
    state.merge([_candidate()])

    cache = state.clear()

    assert cache == {}
    assert state.cache == {}


# --- retention: pruning stale entries ---


def test_merge_prunes_entries_past_retention_window() -> None:
    """An entry whose last_seen predates the retention cutoff is dropped on the next merge."""
    state = ConnectionState(cache_retention_min=5)
    cache = state.merge([_candidate()])
    cache["8.8.8.8|443"]["last_seen"] -= 10 * 60

    cache = state.merge([])

    assert cache == {}


def test_merge_keeps_entries_when_retention_disabled() -> None:
    """cache_retention_min=0 (the default) disables pruning entirely."""
    state = ConnectionState(cache_retention_min=0)
    cache = state.merge([_candidate()])
    cache["8.8.8.8|443"]["last_seen"] -= 10_000 * 60

    cache = state.merge([])

    assert "8.8.8.8|443" in cache


# --- pending verification: AppInfo backfill ---


def test_pending_exe_paths_includes_real_pending_exe() -> None:
    """An application with a real exe and no verification_status yet is pending."""
    state = ConnectionState()
    state.merge([_candidate(exe="/opt/app.exe", app_name="Firefox")])

    assert state.pending_exe_paths() == {"/opt/app.exe"}


def test_pending_exe_paths_excludes_unknown_bucket() -> None:
    """The synthetic unknown-application bucket never contributes a pending exe path."""
    state = ConnectionState()
    state.merge([_candidate(exe=None, process_name="svchost.exe", pid=100)])

    assert state.pending_exe_paths() == set()


def test_pending_exe_paths_excludes_resolved_apps() -> None:
    """An application whose verification has already resolved is not pending."""
    state = ConnectionState()
    state.merge(
        [_candidate(exe="/opt/app.exe", app_name="Firefox", app_verification_status="verified")]
    )

    assert state.pending_exe_paths() == set()


def test_refresh_resolved_applications_backfills_pending_fields() -> None:
    """A hand-fed resolved dict backfills the deferred fields on a matching application."""
    state = ConnectionState()
    state.merge([_candidate(exe="/opt/app.exe", app_name="Firefox")])

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

    app = state.cache["8.8.8.8|443"]["applications"]["/opt/app.exe"]
    assert app["app_creator"] == "Mozilla Corporation"
    assert app["app_verification_status"] == "verified"
    assert app["app_signature_state"] == "SignedAndTrusted"


def test_refresh_resolved_applications_never_overwrites_a_resolved_value() -> None:
    """A later resolved dict never overwrites an already-resolved field (backfill-only)."""
    state = ConnectionState()
    state.merge(
        [
            _candidate(
                exe="/opt/app.exe",
                app_name="Firefox",
                app_verification_status="verified",
            )
        ]
    )

    state.refresh_resolved_applications({"/opt/app.exe": {"app_verification_status": "failed"}})

    assert (
        state.cache["8.8.8.8|443"]["applications"]["/opt/app.exe"]["app_verification_status"]
        == "verified"
    )


def test_refresh_resolved_applications_ignores_unrelated_exe_paths() -> None:
    """Resolved entries for exe paths not present anywhere in the cache are a harmless no-op."""
    state = ConnectionState()
    state.merge([_candidate(exe="/opt/app.exe", app_name="Firefox")])

    state.refresh_resolved_applications(
        {"/opt/other.exe": {"app_verification_status": "verified"}}
    )

    assert (
        state.cache["8.8.8.8|443"]["applications"]["/opt/app.exe"]["app_verification_status"]
        is None
    )


def test_refresh_resolved_applications_updates_entry_whose_connection_has_vanished() -> None:
    """A retained cache entry whose connection has vanished still gets updated."""
    state = ConnectionState()

    # Tick 1: connection present, exe not yet verified.
    state.merge([_candidate(exe="/opt/app.exe", app_name="Firefox")])
    assert state.pending_exe_paths() == {"/opt/app.exe"}

    # Tick 2: connection is gone from the snapshot entirely.
    cache = state.merge([])
    assert "/opt/app.exe" in cache["8.8.8.8|443"]["applications"]
    assert state.pending_exe_paths() == {"/opt/app.exe"}

    # The controller would now call AppInfo.resolved_for(pending_exe_paths())
    # and translate the result into this plain-dict shape.
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

    app = state.cache["8.8.8.8|443"]["applications"]["/opt/app.exe"]
    assert app["app_verification_status"] == "verified"
    assert app["app_creator"] == "Mozilla Corporation"
    assert state.pending_exe_paths() == set()
