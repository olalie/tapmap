"""Tests for SignificantConnections' bounded, chronological history."""

from __future__ import annotations

import pytest

from tapmap.state.significant_connections import MAX_ENTRIES, SignificantConnections


def _events(n: int) -> list[dict[str, int]]:
    return [{"seq": i} for i in range(n)]


@pytest.mark.parametrize(
    ("count",),
    [(0,), (1,), (MAX_ENTRIES,), (MAX_ENTRIES + 1,), (MAX_ENTRIES + 250,)],
)
def test_construction_trims_to_newest_max_entries(count: int) -> None:
    """__init__ trims to the newest MAX_ENTRIES items, trusting the input's chronological order."""
    items = _events(count)

    history = SignificantConnections(items)

    expected = items[-MAX_ENTRIES:]
    assert history.items == expected
    assert len(history.items) <= MAX_ENTRIES


def test_add_appends_as_newest_and_evicts_oldest_when_over_limit() -> None:
    """add() appends to the end; once over MAX_ENTRIES, the oldest entries are evicted."""
    history = SignificantConnections(_events(MAX_ENTRIES))

    history.add({"seq": "new"})

    assert len(history.items) == MAX_ENTRIES
    assert history.items[-1] == {"seq": "new"}
    assert history.items[0] == {"seq": 1}


def test_add_below_limit_does_not_evict() -> None:
    """add() below the limit simply appends without dropping anything."""
    history = SignificantConnections(_events(3))

    history.add({"seq": "new"})

    assert history.items == [{"seq": 0}, {"seq": 1}, {"seq": 2}, {"seq": "new"}]


# --- deferred verification backfill ---


def _event(**overrides: object) -> dict[str, object]:
    """Return a minimal persisted Significant Connection event."""
    event = {
        "timestamp": "2026-08-23T18:42:16.013313",
        "reasons": ["new_app"],
        "pid": 1234,
        "proto": "tcp",
        "ip": "8.8.8.8",
        "port": 443,
        "service": "https",
        "lat": 37.4,
        "lon": -122.1,
        "process_name": "app.exe",
        "exe": "/opt/app.exe",
        "city": "Mountain View",
        "country": "United States",
        "country_code": "US",
        "asn": 15169,
        "asn_org": "Google LLC",
        "app_name": "App",
        "app_creator": None,
        "app_verification_status": None,
        "app_signature_state": None,
        "app_signature_state_details": None,
    }
    event.update(overrides)
    return event


def _resolved(
    exe: str, *, status: str, creator: str = "Vendor Inc."
) -> dict[str, dict[str, object]]:
    """Return a resolved-metadata dict for one exe, matching AppInfo's refresh field shape."""
    return {
        exe: {
            "app_creator": creator,
            "app_verification_status": status,
            "app_signature_state": "SignedAndTrusted",
            "app_signature_state_details": None,
        }
    }


def test_pending_exe_paths_returns_exe_still_awaiting_verification() -> None:
    """pending_exe_paths() includes an event whose verification is still None."""
    history = SignificantConnections([_event(exe="/opt/app.exe", app_verification_status=None)])

    assert history.pending_exe_paths() == {"/opt/app.exe"}


def test_pending_exe_paths_excludes_events_without_exe() -> None:
    """pending_exe_paths() excludes events with no resolvable exe."""
    history = SignificantConnections([_event(exe=None, app_verification_status=None)])

    assert history.pending_exe_paths() == set()


def test_pending_exe_paths_excludes_already_resolved_events() -> None:
    """pending_exe_paths() excludes events whose verification is already terminal."""
    history = SignificantConnections(
        [_event(exe="/opt/app.exe", app_verification_status="verified")]
    )

    assert history.pending_exe_paths() == set()


def test_refresh_resolved_applications_backfills_pending_event_to_verified() -> None:
    """A pending event's verification fields are filled once resolved as verified."""
    history = SignificantConnections([_event(exe="/opt/app.exe")])

    history.refresh_resolved_applications(_resolved("/opt/app.exe", status="verified"))

    event = history.items[0]
    assert event["app_verification_status"] == "verified"
    assert event["app_creator"] == "Vendor Inc."
    assert event["app_signature_state"] == "SignedAndTrusted"


def test_refresh_resolved_applications_backfills_pending_event_to_failed() -> None:
    """A pending event's verification fields are filled once resolved as failed."""
    history = SignificantConnections([_event(exe="/opt/app.exe")])

    history.refresh_resolved_applications(_resolved("/opt/app.exe", status="failed"))

    assert history.items[0]["app_verification_status"] == "failed"


def test_refresh_resolved_applications_backfills_pending_event_to_unknown() -> None:
    """A pending event's verification fields are filled once resolved as unknown."""
    history = SignificantConnections([_event(exe="/opt/app.exe")])

    history.refresh_resolved_applications(_resolved("/opt/app.exe", status="unknown"))

    assert history.items[0]["app_verification_status"] == "unknown"


def test_refresh_resolved_applications_leaves_unrelated_events_unchanged() -> None:
    """An event for a different exe is untouched by an unrelated resolution."""
    event = _event(exe="/opt/other.exe")
    history = SignificantConnections([event])

    history.refresh_resolved_applications(_resolved("/opt/app.exe", status="verified"))

    assert history.items[0]["app_verification_status"] is None
    assert history.items[0] == event


def test_refresh_resolved_applications_leaves_already_final_events_unchanged() -> None:
    """An event with a terminal verification status is not overwritten, even if resolved."""
    history = SignificantConnections(
        [_event(exe="/opt/app.exe", app_verification_status="verified", app_creator="Original")]
    )

    history.refresh_resolved_applications(_resolved("/opt/app.exe", status="failed", creator="New"))

    event = history.items[0]
    assert event["app_verification_status"] == "verified"
    assert event["app_creator"] == "Original"


def test_refresh_resolved_applications_only_changes_verification_related_fields() -> None:
    """Backfilling touches only the four deferred verification fields, nothing else."""
    event = _event(exe="/opt/app.exe")
    original = dict(event)  # snapshot before in-place mutation
    history = SignificantConnections([event])

    history.refresh_resolved_applications(_resolved("/opt/app.exe", status="verified"))

    updated = history.items[0]
    unaffected = {
        "timestamp",
        "reasons",
        "pid",
        "proto",
        "ip",
        "port",
        "service",
        "lat",
        "lon",
        "process_name",
        "exe",
        "city",
        "country",
        "country_code",
        "asn",
        "asn_org",
        "app_name",
    }
    for key in unaffected:
        assert updated[key] == original[key]
    assert updated["app_verification_status"] == "verified"


def test_refresh_resolved_applications_is_a_noop_for_empty_resolved() -> None:
    """An empty resolved dict changes nothing."""
    event = _event(exe="/opt/app.exe")
    history = SignificantConnections([event])

    history.refresh_resolved_applications({})

    assert history.items[0]["app_verification_status"] is None
