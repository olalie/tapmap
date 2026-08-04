"""Test CacheViewBuilder's per-service cache merge, including AppInfo propagation."""

from __future__ import annotations

from typing import Any

from tapmap.ui.cache_view import CacheViewBuilder

_APP_FIELDS = (
    "app_name",
    "app_creator",
    "app_trust",
    "app_signature_state",
    "app_signature_state_reason",
)


def _candidate(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid map candidate (as produced by Model.snapshot())."""
    candidate = {
        "ip": "8.8.8.8",
        "port": 443,
        "proto": "tcp",
        "process_name": None,
        "pid": None,
        "lon": 37.4,
        "lat": -122.1,
        "city": "Mountain View",
        "country": "United States",
        "asn": 15169,
        "asn_org": "Google LLC",
        "app_name": None,
        "app_creator": None,
        "app_trust": None,
        "app_signature_state": None,
        "app_signature_state_reason": None,
    }
    candidate.update(overrides)
    return candidate


def _app_fields(candidate_or_entry: dict[str, Any]) -> dict[str, Any]:
    """Return only the app_* fields from a candidate or entry dict."""
    return {field: candidate_or_entry.get(field) for field in _APP_FIELDS}


def test_merge_map_candidates_propagates_app_fields_into_new_entry() -> None:
    """A new entry carries all five app_* fields from the candidate."""
    builder = CacheViewBuilder()

    candidate = _candidate(
        app_name="Firefox",
        app_creator="Mozilla Corporation",
        app_trust="trusted",
        app_signature_state="SignedAndTrusted",
        app_signature_state_reason="None",
    )

    cache = builder.merge_map_candidates({}, [candidate])
    entry = cache["8.8.8.8|443"]

    assert _app_fields(entry) == {
        "app_name": "Firefox",
        "app_creator": "Mozilla Corporation",
        "app_trust": "trusted",
        "app_signature_state": "SignedAndTrusted",
        "app_signature_state_reason": "None",
    }


def test_merge_map_candidates_leaves_app_fields_none_when_absent() -> None:
    """A candidate with no app data (AppInfo disabled) leaves app_* fields None."""
    builder = CacheViewBuilder()

    cache = builder.merge_map_candidates({}, [_candidate()])
    entry = cache["8.8.8.8|443"]

    assert _app_fields(entry) == dict.fromkeys(_APP_FIELDS)


def test_merge_map_candidates_backfills_app_fields_on_existing_entry() -> None:
    """A later candidate fills in app_* fields that were previously missing."""
    builder = CacheViewBuilder()

    cache = builder.merge_map_candidates({}, [_candidate()])
    cache = builder.merge_map_candidates(
        cache,
        [
            _candidate(
                app_name="Firefox",
                app_creator="Mozilla Corporation",
                app_trust="trusted",
                app_signature_state="SignedAndTrusted",
                app_signature_state_reason="None",
            )
        ],
    )
    entry = cache["8.8.8.8|443"]

    assert entry["app_name"] == "Firefox"
    assert entry["app_trust"] == "trusted"


def test_merge_map_candidates_keeps_first_app_value() -> None:
    """A distinct later value does not overwrite an already-set app_* field."""
    builder = CacheViewBuilder()

    cache = builder.merge_map_candidates(
        {},
        [
            _candidate(
                app_name="Firefox",
                app_creator="Mozilla Corporation",
                app_trust="trusted",
                app_signature_state="SignedAndTrusted",
                app_signature_state_reason="None",
            )
        ],
    )
    cache = builder.merge_map_candidates(
        cache,
        [
            _candidate(
                app_name="Other App",
                app_creator="Other Corp",
                app_trust="not_trusted",
                app_signature_state="SignedAndNotTrusted",
                app_signature_state_reason="NotTrusted",
            )
        ],
    )
    entry = cache["8.8.8.8|443"]

    assert entry["app_name"] == "Firefox"
    assert entry["app_trust"] == "trusted"


def test_build_view_from_cache_output_unaffected_by_app_fields() -> None:
    """Summaries and details do not mention app data."""
    builder = CacheViewBuilder()

    cache = builder.merge_map_candidates(
        {},
        [
            _candidate(
                app_name="Firefox",
                app_creator="Mozilla Corporation",
                app_trust="trusted",
                app_signature_state="SignedAndTrusted",
                app_signature_state_reason="None",
            )
        ],
    )
    view = builder.build_view_from_cache(cache)

    summary = view["summaries"]["0"]
    detail = view["details"]["0"]

    for text in (summary, detail):
        assert "Firefox" not in text
        assert "Mozilla" not in text
        assert "trusted" not in text.lower()
