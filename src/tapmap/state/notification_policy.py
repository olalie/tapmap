"""Evaluate notification eligibility against Insights history."""

from __future__ import annotations

from typing import Any

from .insights import distinct_active_days


def is_learning_period_over(insights: dict[str, Any], min_active_days: int) -> bool:
    """Return whether the notification learning period has ended."""
    return distinct_active_days(insights) >= min_active_days
