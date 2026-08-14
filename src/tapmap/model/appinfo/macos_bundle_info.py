"""Application bundle metadata reader.

Reads CFBundleDisplayName / CFBundleName from an app bundle's Info.plist,
locating the enclosing bundle from an executable path.
"""

from __future__ import annotations

import plistlib
import xml.parsers.expat
from pathlib import Path


def find_bundle_root(exe_path: str) -> Path | None:
    """Return the enclosing .app bundle directory for exe_path, or None.

    Bare (non-bundled) executables have no such ancestor.
    """
    for parent in Path(exe_path).parents:
        if parent.name.endswith(".app"):
            return parent
    return None


def get_bundle_info(exe_path: str) -> dict[str, str | None]:
    """Return {CFBundleDisplayName, CFBundleName} -> str or None.

    Returns an empty dict when there's no enclosing bundle, or when
    Info.plist is missing, malformed, or unreadable.
    """
    bundle_root = find_bundle_root(exe_path)
    if bundle_root is None:
        return {}

    plist_path = bundle_root / "Contents" / "Info.plist"

    try:
        with open(plist_path, "rb") as f:
            data = plistlib.load(f)
    except (OSError, plistlib.InvalidFileException, xml.parsers.expat.ExpatError):
        return {}

    if not isinstance(data, dict):
        return {}

    return {
        "CFBundleDisplayName": data.get("CFBundleDisplayName"),
        "CFBundleName": data.get("CFBundleName"),
    }
