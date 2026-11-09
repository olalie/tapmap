"""Evaluate and record notification eligibility against Insights history."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from .insights import active_day_ordinals
from .insights_state import InsightsState


def is_learning_period_over(insights_state: InsightsState, min_active_days: int) -> bool:
    """Return whether notifications may be sent.

    True if min_active_days is 0 or the learning period completion is recorded.
    """
    return min_active_days == 0 or insights_state.notification_learning_completed_day is not None


def record_learning_completion(
    insights_state: InsightsState,
    min_active_days: int,
    today: int,
    extra_active_days: Iterable[int] = (),
) -> bool:
    """Record today as the learning completion day once enough active days exist.

    Count the distinct Insights active days together with extra_active_days.
    Never record for min_active_days 0 and never overwrite a recorded day.
    Return True if completion was recorded by this call.
    """
    if min_active_days == 0 or insights_state.notification_learning_completed_day is not None:
        return False

    active_days = active_day_ordinals(insights_state.insights) | set(extra_active_days)
    if len(active_days) < min_active_days:
        return False

    insights_state.notification_learning_completed_day = today
    return True


def event_day_ordinals(events: Iterable[dict[str, Any]]) -> set[int]:
    """Return the date ordinals of the Significant Connection event timestamps.

    Skip events without a valid ISO timestamp string.
    """
    days: set[int] = set()
    for event in events:
        timestamp = event.get("timestamp")
        if not isinstance(timestamp, str):
            continue
        try:
            days.add(datetime.fromisoformat(timestamp).date().toordinal())
        except ValueError:
            continue
    return days
