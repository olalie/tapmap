"""Complete persisted contents of insights.json."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CURRENT_SCHEMA_VERSION = 2


@dataclass
class InsightsState:
    """Insights history plus verification-failure history, persisted as one unit.

    insights: the four 30-day rolling dimensions (countries, providers, ports,
    applications), each {value: {"l": anchor_day, "m": bitmask}}. Mutated
    externally by process_insights().

    verification_failed: {app_name: last_failed_seen_day}. Mutated externally
    by SignificanceHistory, which holds this dict by reference, not a copy.
    """

    version: int
    insights: dict[str, Any]
    verification_failed: dict[str, int]
