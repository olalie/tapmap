"""Tests for the notification learning-period policy."""

from __future__ import annotations

from typing import Any

from tapmap.state.notification_policy import is_learning_period_over


def _insights_with_active_days(n: int) -> dict[str, Any]:
    """Return an insights dict whose countries dimension has exactly n distinct active days."""
    mask = (1 << n) - 1 if n > 0 else 0
    return {"countries": {"US": {"l": 1, "m": mask}}}


def test_below_threshold_is_not_eligible() -> None:
    """Fewer active days than the threshold: learning period is not over."""
    insights = _insights_with_active_days(6)
    assert is_learning_period_over(insights, min_active_days=7) is False


def test_exactly_at_threshold_is_eligible() -> None:
    """Exactly the threshold's worth of active days: learning period is over (>=, not >)."""
    insights = _insights_with_active_days(7)
    assert is_learning_period_over(insights, min_active_days=7) is True


def test_above_threshold_is_eligible() -> None:
    """More active days than the threshold: learning period is over."""
    insights = _insights_with_active_days(10)
    assert is_learning_period_over(insights, min_active_days=7) is True


def test_empty_insights_is_not_eligible_for_positive_threshold() -> None:
    """No history at all: not eligible when the threshold is positive."""
    assert is_learning_period_over({}, min_active_days=7) is False


def test_zero_threshold_is_always_eligible() -> None:
    """A zero threshold disables the learning period: always eligible, even with no history."""
    assert is_learning_period_over({}, min_active_days=0) is True
