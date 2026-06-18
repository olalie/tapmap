"""Persistence and orchestration helpers for insights data."""

import json
from pathlib import Path
from typing import Any

from tapmap.state.daily_report import DailyReportData, build_report_data


def load_insights(path: Path) -> dict[str, Any]:
    """Load insights from a JSON file, restoring historical contract.

    Args:
        path: Path to the insights file.

    Returns:
        Normalized insights dict with only the four expected keys.

    Raises:
        OSError, json.JSONDecodeError
    """
    expected_keys = {"countries", "providers", "ports", "applications"}
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        insights = data.get("insights")
        if not isinstance(insights, dict):
            raise ValueError("insights is not a dict")
        normalized = {
            k: dict(insights[k]) if isinstance(insights.get(k), dict) else {}
            for k in expected_keys
        }
        return normalized
    except Exception:
        return {k: {} for k in ["countries", "providers", "ports", "applications"]}


def save_insights(path: Path, data: dict[str, Any]) -> None:
    """Save insights to a JSON file, using historical wrapper contract.

    Args:
        path: Path to the insights file.
        data: Raw dict to save.

    Raises:
        OSError
    """
    tmp_path = path.with_suffix(".tmp")

    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(
            {"insights": data},
            f,
            ensure_ascii=False,
            indent=2,
        )
        f.flush()

    tmp_path.replace(path)


def build_daily_report(insights: dict[str, Any]) -> DailyReportData:
    """Build daily report data from insights.

    Args:
        insights: Raw insights dict.

    Returns:
        DailyReportData TypedDict.
    """
    return build_report_data(insights)
