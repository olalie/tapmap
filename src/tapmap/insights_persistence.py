"""Persistence and orchestration helpers for insights data."""

import json
import time
from pathlib import Path
from typing import Any

from tapmap.state.daily_report import DailyReportData, build_report_data
from tapmap.state.insights_state import CURRENT_SCHEMA_VERSION, InsightsState

_DIMENSION_KEYS = ("countries", "providers", "ports", "applications")
_APP_NAME_KEYED_SCHEMA_VERSION = 2


def _empty_insights_dict() -> dict[str, Any]:
    return {k: {} for k in _DIMENSION_KEYS}


def load_insights(path: Path) -> InsightsState:
    """Load InsightsState from a JSON file, migrating older schema versions as needed.

    A file with no version marker, or version < 2, has its applications
    history reset (process-name-keyed history cannot be reliably converted
    to app_name-keyed history); countries, providers, and ports are preserved.

    Args:
        path: Path to the insights file.

    Returns:
        InsightsState at the current schema version. Empty if the file is missing.

    Raises:
        ValueError: If the file is not valid JSON or its top-level structure is malformed.
        OSError: If the file exists but cannot be read.
    """
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return InsightsState(
            version=CURRENT_SCHEMA_VERSION,
            insights=_empty_insights_dict(),
            verification_failed={},
        )

    if not isinstance(data, dict):
        raise ValueError("insights file is not a JSON object")

    version = data.get("version")
    version = version if isinstance(version, int) else 1

    raw_insights = data.get("insights")
    if not isinstance(raw_insights, dict):
        raise ValueError("insights is not a dict")

    insights = {
        k: dict(raw_insights[k]) if isinstance(raw_insights.get(k), dict) else {}
        for k in _DIMENSION_KEYS
    }

    raw_verification_failed = data.get("verification_failed")
    verification_failed = (
        dict(raw_verification_failed) if isinstance(raw_verification_failed, dict) else {}
    )

    if version < _APP_NAME_KEYED_SCHEMA_VERSION:
        insights["applications"] = {}
        version = CURRENT_SCHEMA_VERSION

    learning_completed_day = data.get("notification_learning_completed_day")

    return InsightsState(
        version=version,
        insights=insights,
        verification_failed=verification_failed,
        significance_last_seen=_parse_significance_last_seen(data.get("significance_last_seen")),
        notification_learning_completed_day=(
            learning_completed_day if isinstance(learning_completed_day, int) else None
        ),
    )


def _parse_significance_last_seen(raw: Any) -> dict[str, dict[Any, int]]:
    """Return {dimension: {value: day}} from raw, dropping malformed entries.

    Convert port values to int. Return an empty dict if raw is not a dict.
    """
    if not isinstance(raw, dict):
        return {}

    last_seen: dict[str, dict[Any, int]] = {}
    for dimension in _DIMENSION_KEYS:
        raw_entries = raw.get(dimension)
        if not isinstance(raw_entries, dict):
            continue
        entries: dict[Any, int] = {}
        for key, day in raw_entries.items():
            if not isinstance(day, int):
                continue
            if dimension == "ports":
                try:
                    entries[int(key)] = day
                except ValueError:
                    continue
            else:
                entries[key] = day
        last_seen[dimension] = entries
    return last_seen


def save_insights(path: Path, state: InsightsState) -> None:
    """Save InsightsState to a JSON file as one atomic unit.

    Args:
        path: Path to the insights file.
        state: InsightsState to persist.

    Raises:
        OSError: If the insights file cannot be written or replaced.
    """
    tmp_path = path.with_suffix(".tmp")

    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "version": state.version,
                "insights": state.insights,
                "verification_failed": state.verification_failed,
                "significance_last_seen": state.significance_last_seen,
                "notification_learning_completed_day": state.notification_learning_completed_day,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
        f.flush()

    # The temporary file has been closed. Retry the atomic replace in
    # case another process briefly locks the destination file.
    for attempt in range(6):
        try:
            tmp_path.replace(path)
            return

        except OSError:
            if attempt == 5:
                raise

            time.sleep(1)


def build_daily_report(insights: dict[str, Any]) -> DailyReportData:
    """Build daily report data from insights.

    Args:
        insights: Raw insights dict.

    Returns:
        DailyReportData TypedDict.
    """
    return build_report_data(insights)
