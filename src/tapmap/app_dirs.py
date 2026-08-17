"""Application data directory and folder access utilities.

Resolve per-user application data paths and provide
helpers for creating and opening the directory.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Final

APP_NAME: Final[str] = "TapMap"
README_VERSION: Final[int] = 1

README_TEXT: Final[str] = (
    f"TAPMAP_README_VERSION={README_VERSION}\n"
    "\n"
    "GeoIP databases used by TapMap.\n"
    "\n"
    "Recommended: install databases from GeoIP Database Management in TapMap.\n"
    "\n"
    "Manual installation is also supported.\n"
    "\n"
    "If running in Docker, this folder is mapped from the host to /data in the container.\n"
    "\n"
    "Supported providers:\n"
    "\n"
    "MaxMind GeoLite2\n"
    "- GeoLite2-City.mmdb\n"
    "- GeoLite2-ASN.mmdb\n"
    "- https://dev.maxmind.com/geoip/geolite2-free-geolocation-data\n"
    "\n"
    "DB-IP Lite\n"
    "- DBIP-City.mmdb\n"
    "- DBIP-ASN.mmdb\n"
    "- DB-IP files must be renamed to the filenames above.\n"
    "- https://db-ip.com/db/lite.php\n"
)


def get_native_app_data_dir(app_name: str = APP_NAME) -> Path:
    r"""Return the per-user application data directory for the current OS.

    Windows: %APPDATA%\<app_name>
    macOS:   ~/Library/Application Support/<app_name>
    Linux:   ${XDG_DATA_HOME:-~/.local/share}/<app_name>
    """
    system = platform.system()

    if system == "Windows":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / app_name
        return Path.home() / "AppData" / "Roaming" / app_name

    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / app_name

    xdg = os.environ.get("XDG_DATA_HOME")
    base_dir = Path(xdg) if xdg else (Path.home() / ".local" / "share")
    return base_dir / app_name


def _readme_needs_update(readme: Path) -> bool:
    """Return True when README.txt is missing or outdated."""
    if not readme.exists():
        return True

    try:
        text = readme.read_text(encoding="utf-8")
        first_line = text.splitlines()[0] if text else ""

        return first_line != f"TAPMAP_README_VERSION={README_VERSION}"

    except Exception:
        return True


def ensure_app_data_dir(app_dir: Path) -> None:
    """Create the application data directory and README.txt file when missing."""
    app_dir = app_dir.expanduser()
    app_dir.mkdir(parents=True, exist_ok=True)

    readme = app_dir / "README.txt"

    if _readme_needs_update(readme):
        readme.write_text(README_TEXT, encoding="utf-8")


def ensure_native_app_data_dir(app_name: str = APP_NAME) -> Path:
    """Return native app data directory and ensure it exists."""
    app_dir = get_native_app_data_dir(app_name)
    ensure_app_data_dir(app_dir)
    return app_dir


def open_folder(path: Path) -> tuple[bool, str]:
    """Open a folder in the system file manager.

    Returns:
        ok: True on success.
        message: Status message suitable for UI.
    """
    try:
        path = path.expanduser()
        path.mkdir(parents=True, exist_ok=True)

        system = platform.system()

        if system == "Windows":
            # os.startfile() would not bring Explorer to the foreground here.
            subprocess.Popen(["explorer", str(path)])
            return True, f"Opened: {path}"

        if system == "Darwin":
            subprocess.Popen(["open", str(path)])
            return True, f"Opened: {path}"

        xdg_open = shutil.which("xdg-open")
        if not xdg_open:
            return False, "xdg-open is not available on this system."

        cp = subprocess.run([xdg_open, str(path)], capture_output=True, text=True, check=False)
        if cp.returncode == 0:
            return True, f"Opened: {path}"

        detail = (cp.stderr or cp.stdout or "").strip()
        msg = "xdg-open failed."
        if detail:
            msg += f" {detail}"
        return False, msg

    except Exception as exc:
        return False, f"Failed to open folder: {path}. Error: {exc}"


def open_file(path: Path) -> tuple[bool, str]:
    """Open path with the system default application."""
    try:
        path = path.expanduser()
        if not path.is_file():
            return False, f"File not found: {path}"

        system = platform.system()

        if system == "Windows":
            os.startfile(str(path))
            return True, f"Opened: {path}"

        if system == "Darwin":
            subprocess.Popen(["open", str(path)])
            return True, f"Opened: {path}"

        xdg_open = shutil.which("xdg-open")
        if not xdg_open:
            return False, "xdg-open is not available on this system."

        cp = subprocess.run([xdg_open, str(path)], capture_output=True, text=True, check=False)
        if cp.returncode == 0:
            return True, f"Opened: {path}"

        detail = (cp.stderr or cp.stdout or "").strip()
        msg = "xdg-open failed."
        if detail:
            msg += f" {detail}"
        return False, msg

    except Exception as exc:
        return False, f"Failed to open file: {path}. Error: {exc}"


def reveal_in_file_manager(path: Path) -> tuple[bool, str]:
    """Reveal a file in the system file manager, selecting it when supported.

    Windows: File Explorer with the file selected. macOS: Finder with the
    file selected. Linux: the file manager's own item-selection support via
    the freedesktop.org FileManager1 D-Bus interface (Nautilus, Nemo, and
    similar), when available; otherwise falls back to opening the containing
    folder without a selection.

    Returns:
        ok: True on success.
        message: Status message suitable for UI.
    """
    try:
        path = path.expanduser()
        if not path.is_file():
            return False, f"File not found: {path}"

        system = platform.system()

        if system == "Windows":
            # explorer's /select, switch must stay unquoted, immediately
            # followed by the path in its own quotes: /select,"C:\a b\f.exe".
            # Passing ["explorer", "/select,C:\\a b\\f.exe"] as a list makes
            # subprocess quote that whole token together via list2cmdline
            # (since it contains a space), producing "/select,C:\a b\f.exe"
            # as one unit - a form Explorer fails to parse, silently falling
            # back to a default folder instead of erroring. Passing a plain
            # string bypasses list2cmdline entirely (CPython's
            # subprocess.py: `if isinstance(args, str): pass`), so the
            # command line reaches CreateProcess exactly as written here.
            subprocess.Popen(f'explorer /select,"{path}"')
            return True, f"Revealed: {path}"

        if system == "Darwin":
            subprocess.Popen(["open", "-R", str(path)])
            return True, f"Revealed: {path}"

        dbus_send = shutil.which("dbus-send")
        if dbus_send:
            cp = subprocess.run(
                [
                    dbus_send,
                    "--session",
                    "--dest=org.freedesktop.FileManager1",
                    "--type=method_call",
                    "/org/freedesktop/FileManager1",
                    "org.freedesktop.FileManager1.ShowItems",
                    f"array:string:{path.as_uri()}",
                    "string:",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if cp.returncode == 0:
                return True, f"Revealed: {path}"

        return open_folder(path.parent)

    except Exception as exc:
        return False, f"Failed to reveal file: {path}. Error: {exc}"
