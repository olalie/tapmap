"""Persistence for the Significant Connections history."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_SCHEMA_VERSION = 1


def load_significant_connections(path: Path) -> list[dict[str, Any]]:
    """Load Significant Connections events from a JSON file.

    Args:
        path: Path to the significant_connections file.

    Returns:
        List of event dicts, oldest first. Empty if the file is missing,
        corrupt, or malformed; malformed individual records are dropped.
    """
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)

        events = data.get("events")
        if not isinstance(events, list):
            return []

        return [event for event in events if isinstance(event, dict)]
    except Exception:
        return []


def save_significant_connections(path: Path, events: list[dict[str, Any]]) -> None:
    """Save Significant Connections events to a JSON file.

    Args:
        path: Path to the significant_connections file.
        events: List of event dicts, oldest first.

    Raises:
        OSError: If the file cannot be written or replaced.
    """
    tmp_path = path.with_suffix(".tmp")

    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(
            {"schema_version": _SCHEMA_VERSION, "events": events},
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
