"""Tests for the notification learning-period policy."""

from __future__ import annotations

from typing import Any

from tapmap.state.notification_policy import is_learning_period_over


def _insights_with_active_days(n: int) -> dict[str, Any]:
    """Return Insights with the requested number of active days."""
    mask = (1 << n) - 1 if n > 0 else 0
    return {"countries": {"US": {"l": 1, "m": mask}}}


def test_below_threshold_is_not_eligible() -> None:
    insights = _insights_with_active_days(6)
    assert is_learning_period_over(insights, min_active_days=7) is False


def test_exactly_at_threshold_is_eligible() -> None:
    insights = _insights_with_active_days(7)
    assert is_learning_period_over(insights, min_active_days=7) is True


def test_above_threshold_is_eligible() -> None:
    insights = _insights_with_active_days(10)
    assert is_learning_period_over(insights, min_active_days=7) is True


def test_empty_insights_is_not_eligible_for_positive_threshold() -> None:
    assert is_learning_period_over({}, min_active_days=7) is False


def test_zero_threshold_is_always_eligible() -> None:
    assert is_learning_period_over({}, min_active_days=0) is True
