"""Complete persisted contents of insights.json."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CURRENT_SCHEMA_VERSION = 2


@dataclass
class InsightsState:
    """Insights history plus significance history, persisted as one unit.

    insights: the four 30-day rolling dimensions (countries, providers, ports,
    applications), each {value: {"l": anchor_day, "m": bitmask}}. Mutated
    externally by process_insights().

    verification_failed: {app_name: last_failed_seen_day}. Mutated externally
    by SignificanceHistory, which holds this dict by reference, not a copy.

    significance_last_seen: {dimension: {value: last_seen_day}} for the four
    dimensions, including values seen only on unmapped connections; port
    values are int. Mutated externally by SignificanceHistory, which holds
    this dict by reference, not a copy.

    notification_learning_completed_day: date ordinal on which the
    notification learning period completed, or None while learning. Once
    set, it is never cleared.
    """

    version: int
    insights: dict[str, Any]
    verification_failed: dict[str, int]
    significance_last_seen: dict[str, dict[Any, int]] = field(default_factory=dict)
    notification_learning_completed_day: int | None = None
