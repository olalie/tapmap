"""Tests for SignificanceHistory reconstruction and get_significant() evaluation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from tapmap.state.insights_state import InsightsState
from tapmap.state.significance import (
    REASON_NEW_APP,
    REASON_NEW_COUNTRY,
    REASON_NEW_PORT,
    REASON_NEW_PROVIDER,
    REASON_VERIFICATION_FAILED,
    SignificanceHistory,
    get_significant,
)


def _cache_item(**overrides: Any) -> dict[str, Any]:
    item = {
        "proto": "tcp",
        "ip": "8.8.8.8",
        "port": 443,
        "service": "https",
        "lat": 37.4,
        "lon": -122.1,
        "process_name": "chrome.exe",
        "exe": r"C:\chrome.exe",
        "city": "Mountain View",
        "country": "United States",
        "country_code": "US",
        "asn": 15169,
        "asn_org": "Google LLC",
        "app_name": "Google Chrome",
        "app_creator": "Google LLC",
        "app_verification_status": "verified",
        "app_signature_state": None,
        "app_signature_state_details": None,
        "pid": 1234,
    }
    item.update(overrides)
    return item


def _bitmask_entry(anchor_day: int, days_ago_seen: int) -> dict[str, int]:
    """Return a {l, m} entry recording one observation days_ago_seen days before anchor_day."""
    return {"l": anchor_day, "m": 1 << days_ago_seen}


def _empty_last_seen() -> dict[str, dict[Any, int]]:
    return {"countries": {}, "providers": {}, "ports": {}, "applications": {}}


# --- SignificanceHistory.from_insights_state ---


def test_from_insights_state_reconstructs_last_seen_and_shares_verification_failed() -> None:
    """last_seen is derived from Insights bitmasks; verification_failed is shared by reference."""
    today = datetime(2026, 8, 22).date().toordinal()
    verification_failed = {"BadApp": today - 5}
    insights_state = InsightsState(
        version=2,
        insights={
            "countries": {"US": _bitmask_entry(today, 2)},
            "providers": {"Google LLC": _bitmask_entry(today, 0)},
            "ports": {"443": _bitmask_entry(today, 10)},
            "applications": {"Google Chrome": _bitmask_entry(today, 1)},
        },
        verification_failed=verification_failed,
    )

    history = SignificanceHistory.from_insights_state(insights_state)

    assert history.last_seen["countries"]["US"] == today - 2
    assert history.last_seen["providers"]["Google LLC"] == today
    assert history.last_seen["ports"][443] == today - 10
    assert isinstance(next(iter(history.last_seen["ports"].keys())), int)
    assert history.last_seen["applications"]["Google Chrome"] == today - 1
    assert history.verification_failed is verification_failed


def test_from_insights_state_skips_zeroed_and_malformed_entries() -> None:
    """Entries with m == 0 or non-int port keys are silently skipped, not treated as errors."""
    today = datetime(2026, 8, 22).date().toordinal()
    insights_state = InsightsState(
        version=2,
        insights={
            "countries": {"XX": {"l": today, "m": 0}},
            "providers": {},
            "ports": {"not-a-port": _bitmask_entry(today, 0)},
            "applications": {},
        },
        verification_failed={},
    )

    history = SignificanceHistory.from_insights_state(insights_state)

    assert history.last_seen["countries"] == {}
    assert history.last_seen["ports"] == {}


# --- check_and_update: 30-day boundary ---


@pytest.mark.parametrize(
    ("days_since_last_seen", "expected_is_new"),
    [
        (0, False),
        (1, False),
        (29, False),
        (30, True),
        (31, True),
    ],
)
def test_check_and_update_30_day_boundary(
    days_since_last_seen: int, expected_is_new: bool
) -> None:
    """A value is new again once it has been at least 30 days since it was last recorded."""
    today = 738000
    history = SignificanceHistory(
        last_seen={**_empty_last_seen(), "countries": {"US": today - days_since_last_seen}},
        verification_failed={},
    )

    assert history.check_and_update("countries", "US", today) is expected_is_new
    # Always updates, regardless of outcome.
    assert history.last_seen["countries"]["US"] == today


def test_check_and_update_unseen_value_is_new() -> None:
    """A value never seen before is new."""
    history = SignificanceHistory(last_seen=_empty_last_seen(), verification_failed={})

    assert history.check_and_update("countries", "US", 738000) is True
    assert history.last_seen["countries"]["US"] == 738000


# --- get_significant: reason/dimension mapping and event shape ---


def test_get_significant_returns_none_when_nothing_is_new() -> None:
    """A connection whose app/country/provider/port were all already seen produces no event."""
    today = 738000
    history = SignificanceHistory(
        last_seen={
            "countries": {"US": today},
            "providers": {"Google LLC": today},
            "ports": {443: today},
            "applications": {"Google Chrome": today},
        },
        verification_failed={},
    )

    result = get_significant(_cache_item(), history, datetime.fromordinal(today))

    assert result is None


def test_get_significant_new_connection_reports_all_four_new_reasons() -> None:
    """A connection novel in all four dimensions produces one event with all four reasons."""
    history = SignificanceHistory(last_seen=_empty_last_seen(), verification_failed={})

    result = get_significant(_cache_item(), history, datetime(2026, 8, 22))

    assert result is not None
    assert set(result["reasons"]) == {
        REASON_NEW_APP,
        REASON_NEW_COUNTRY,
        REASON_NEW_PROVIDER,
        REASON_NEW_PORT,
    }


def test_get_significant_event_preserves_full_connection_detail() -> None:
    """The event carries the documented fields plus timestamp/reasons/pid, and drops the rest."""
    history = SignificanceHistory(last_seen=_empty_last_seen(), verification_failed={})
    now = datetime(2026, 8, 22, 10, 30, 0)

    result = get_significant(_cache_item(), history, now)

    assert result is not None
    assert result["timestamp"] == now.isoformat()
    assert result["pid"] == 1234
    assert result["ip"] == "8.8.8.8"
    assert result["app_name"] == "Google Chrome"
    assert "cmdline" not in result
    assert "service_hint" not in result
    assert "process_status" not in result
    assert "service_scope" not in result
    assert "connection_key" not in result


def test_get_significant_verification_failed_reason() -> None:
    """A FAILED verification status on an already-known app produces only verification_failed."""
    today_dt = datetime(2026, 8, 22)
    today = today_dt.date().toordinal()
    history = SignificanceHistory(
        last_seen={
            "countries": {"US": today},
            "providers": {"Google LLC": today},
            "ports": {443: today},
            "applications": {"Google Chrome": today},
        },
        verification_failed={},
    )

    result = get_significant(_cache_item(app_verification_status="failed"), history, today_dt)

    assert result is not None
    assert result["reasons"] == [REASON_VERIFICATION_FAILED]


def test_get_significant_missing_app_name_excludes_new_app_and_verification_failed_only() -> None:
    """No app_name means new_app/verification_failed can't be evaluated; other reasons still can."""
    history = SignificanceHistory(last_seen=_empty_last_seen(), verification_failed={})

    result = get_significant(
        _cache_item(app_name=None, app_verification_status="failed"),
        history,
        datetime(2026, 8, 22),
    )

    assert result is not None
    assert REASON_NEW_APP not in result["reasons"]
    assert REASON_VERIFICATION_FAILED not in result["reasons"]
    assert REASON_NEW_COUNTRY in result["reasons"]


# --- realistic multi-poll scenarios ---


def test_first_connection_owns_new_reason_within_one_poll() -> None:
    """When two connections in one poll introduce the same new country, only the first gets it."""
    history = SignificanceHistory(last_seen=_empty_last_seen(), verification_failed={})
    now = datetime(2026, 8, 22)

    first = get_significant(_cache_item(ip="1.1.1.1", port=80), history, now)
    second = get_significant(_cache_item(ip="2.2.2.2", port=80), history, now)

    assert first is not None
    assert REASON_NEW_COUNTRY in first["reasons"]
    assert second is None


def test_significance_across_polls_deduplicates_then_becomes_new_again_after_30_days() -> None:
    """A value stays non-new across polls until 30 days have passed since it was last recorded.

    check_and_update() refreshes last_seen on every call, including
    duplicate (non-new) observations, so the 30-day window is measured from
    day2 (the last observation), not day1 (the first).
    """
    history = SignificanceHistory(last_seen=_empty_last_seen(), verification_failed={})
    day1 = datetime(2026, 1, 1)
    day2 = datetime(2026, 1, 2)
    day_after_30_more = datetime(2026, 2, 1)

    poll1 = get_significant(_cache_item(), history, day1)
    poll2 = get_significant(_cache_item(), history, day2)
    poll3 = get_significant(_cache_item(), history, day_after_30_more)

    assert poll1 is not None
    assert REASON_NEW_COUNTRY in poll1["reasons"]
    assert poll2 is None
    assert poll3 is not None
    assert REASON_NEW_COUNTRY in poll3["reasons"]
