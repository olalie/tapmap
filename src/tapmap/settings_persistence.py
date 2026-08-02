"""Persistence helpers for user interface settings."""

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """User interface settings persisted across sessions."""

    version: int = 1
    insights_panel: bool = True
    technical_details: bool = False


DEFAULT_SETTINGS = Settings()


def load_settings(path: Path) -> Settings:
    """Load settings from a JSON file, falling back to defaults.

    Args:
        path: Path to the settings file.

    Returns:
        Settings loaded from disk, or defaults on any error.
    """
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("settings is not a dict")
        return Settings(
            version=DEFAULT_SETTINGS.version,
            insights_panel=bool(data.get("insights_panel", DEFAULT_SETTINGS.insights_panel)),
            technical_details=bool(
                data.get("technical_details", DEFAULT_SETTINGS.technical_details)
            ),
        )
    except Exception:
        return DEFAULT_SETTINGS


def save_settings(path: Path, settings: Settings) -> None:
    """Save settings to a JSON file atomically.

    Args:
        path: Path to the settings file.
        settings: Settings to save.

    Raises:
        OSError
    """
    tmp_path = path.with_suffix(".tmp")

    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(asdict(settings), f, ensure_ascii=False, indent=2)
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