"""Decide whether the notification learning period has elapsed.

Pure and read-only with respect to Insights: does not age, mutate, or persist
anything. Reason-agnostic by design - no Significant Connection reason
bypasses this check.
"""

from __future__ import annotations

from typing import Any

from .insights import distinct_active_days


def is_learning_period_over(insights: dict[str, Any], min_active_days: int) -> bool:
    """Return whether at least min_active_days of Insights history exist."""
    return distinct_active_days(insights) >= min_active_days
