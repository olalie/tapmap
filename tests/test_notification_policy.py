"""Tests for the notification learning-period policy."""

from __future__ import annotations

from typing import Any

from tapmap.state.insights_state import InsightsState
from tapmap.state.notification_policy import (
    event_day_ordinals,
    is_learning_period_over,
    record_learning_completion,
)

_TODAY = 739928


def _insights_state(active_days: int = 0, completed_day: int | None = None) -> InsightsState:
    """Return an InsightsState with active_days consecutive days ending on _TODAY."""
    mask = (1 << active_days) - 1
    insights: dict[str, Any] = {"countries": {"US": {"l": _TODAY, "m": mask}}}
    return InsightsState(
        version=2,
        insights=insights,
        verification_failed={},
        notification_learning_completed_day=completed_day,
    )


def test_learning_period_is_not_over_without_recorded_completion() -> None:
    """Return False for a positive threshold until completion is recorded."""
    assert is_learning_period_over(_insights_state(active_days=10), min_active_days=7) is False


def test_recorded_completion_ends_learning_for_any_threshold() -> None:
    """Return True once completion is recorded, also after the threshold is raised."""
    insights_state = _insights_state(completed_day=_TODAY - 40)

    assert is_learning_period_over(insights_state, min_active_days=30) is True


def test_zero_threshold_ends_learning_without_recorded_completion() -> None:
    """Return True for a threshold of 0."""
    assert is_learning_period_over(_insights_state(), min_active_days=0) is True


def test_record_below_threshold_records_nothing() -> None:
    """Leave completion unrecorded below the threshold."""
    insights_state = _insights_state(active_days=6)

    assert record_learning_completion(insights_state, 7, _TODAY) is False
    assert insights_state.notification_learning_completed_day is None


def test_record_at_threshold_records_today_once() -> None:
    """Record today at the threshold and keep the first recorded day on later calls."""
    insights_state = _insights_state(active_days=7)

    assert record_learning_completion(insights_state, 7, _TODAY) is True
    assert record_learning_completion(insights_state, 7, _TODAY + 1) is False
    assert insights_state.notification_learning_completed_day == _TODAY


def test_record_with_zero_threshold_records_nothing() -> None:
    """Never record completion for a threshold of 0."""
    insights_state = _insights_state(active_days=7)

    assert record_learning_completion(insights_state, 0, _TODAY) is False
    assert insights_state.notification_learning_completed_day is None


def test_record_counts_extra_days_once_with_insights_days() -> None:
    """Count the union of Insights days and extra days toward the threshold."""
    insights_state = _insights_state(active_days=4)
    overlapping_and_older_days = {_TODAY, _TODAY - 1, _TODAY - 40, _TODAY - 41, _TODAY - 42}

    assert record_learning_completion(insights_state, 7, _TODAY, overlapping_and_older_days)
    assert insights_state.notification_learning_completed_day == _TODAY


def test_event_day_ordinals_skips_invalid_timestamps() -> None:
    """Return the distinct event dates and skip missing or invalid timestamps."""
    events: list[dict[str, Any]] = [
        {"timestamp": "2026-10-23T10:29:20.123456"},
        {"timestamp": "2026-10-23T18:35:44"},
        {"timestamp": "2026-11-08T10:48:07"},
        {"timestamp": "not-a-timestamp"},
        {"timestamp": None},
        {},
    ]

    assert event_day_ordinals(events) == {
        739912,
        739928,
    }
