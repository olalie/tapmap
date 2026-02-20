from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Final

APP_NAME: Final[str] = "TapMap"

README_TEXT: Final[str] = (
    "Place GeoIP .mmdb databases here.\n"
    "Required files:\n"
    "- GeoLite2-City.mmdb\n"
    "- GeoLite2-ASN.mmdb\n"
    "\n"
    "Download (free, account required):\n"
    "https://dev.maxmind.com/geoip/geolite2-free-geolocation-data\n"
)


def get_app_data_dir(app_name: str = APP_NAME) -> Path:
    r"""Return the per-user application data directory for the current OS.

    Windows: %APPDATA%\<app_name>
    macOS:   ~/Library/Application Support/<app_name>
    Linux:   ${XDG_DATA_HOME:-~/.local/share}/<app_name>
    """
    system = platform.system()

    if system == "Windows":
        base = os.environ.get("APPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Roaming")
        return Path(base) / app_name

    if system == "Darwin":  # macOS
        return Path.home() / "Library" / "Application Support" / app_name

    xdg = os.environ.get("XDG_DATA_HOME")
    base_dir = Path(xdg) if xdg else (Path.home() / ".local" / "share")
    return base_dir / app_name


def ensure_app_data_dir(app_dir: Path) -> None:
    """Create the application data directory and README.txt file when missing."""
    app_dir.mkdir(parents=True, exist_ok=True)
    readme = app_dir / "README.txt"
    if not readme.exists():
        readme.write_text(README_TEXT, encoding="utf-8")


def get_or_create_app_data_dir(app_name: str = APP_NAME) -> Path:
    """Return the per-user application data directory, creating it when missing."""
    app_dir = get_app_data_dir(app_name)
    ensure_app_data_dir(app_dir)
    return app_dir


def open_folder(path: Path) -> tuple[bool, str]:
    """Open a folder in the system file manager.

    Returns:
        ok: True on success.
        message: Status message.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)

        system = platform.system()
        if system == "Windows":
            subprocess.Popen(["explorer.exe", str(path)])
            return True, f"Opened: {path}"

        if system == "Darwin":
            subprocess.Popen(["open", str(path)])
            return True, f"Opened: {path}"

        subprocess.Popen(["xdg-open", str(path)])
        return True, f"Opened: {path}"

    except Exception as exc:
        return False, f"Failed to open folder: {path}. Error: {exc}"