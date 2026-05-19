"""Persistence and orchestration helpers for insights data."""

import json
from pathlib import Path
from typing import Any

from tapmap.state.daily_report import DailyReportData, build_report_data


def load_insights(path: Path) -> dict[str, Any]:
    """Load insights from a JSON file.

    Args:
        path: Path to the insights file.

    Returns:
        Raw dict loaded from JSON.

    Raises:
        OSError, json.JSONDecodeError
    """
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_insights(path: Path, data: dict[str, Any]) -> None:
    """Save insights to a JSON file.

    Args:
        path: Path to the insights file.
        data: Raw dict to save.

    Raises:
        OSError
    """
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_daily_report(insights: dict[str, Any]) -> DailyReportData:
    """Build daily report data from insights.

    Args:
        insights: Raw insights dict.

    Returns:
        DailyReportData TypedDict.
    """
    return build_report_data(insights)
