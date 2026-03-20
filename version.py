"""Provide application version from installed metadata or pyproject.toml."""

from __future__ import annotations

import sys
from importlib import metadata
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


_PROJECT_NAME = "tapmap"
_DISPLAY_PREFIX = "v"


def get_display_version() -> str:
    """Return version string formatted for UI and CLI."""
    version = _read_version()
    return version if version.startswith(_DISPLAY_PREFIX) else f"{_DISPLAY_PREFIX}{version}"


def _read_version() -> str:
    """Return canonical application version."""
    installed_version = _read_installed_version()
    if installed_version is not None:
        return installed_version

    return _read_pyproject_version()


def _read_installed_version() -> str | None:
    """Return installed package version if available."""
    try:
        return metadata.version(_PROJECT_NAME)
    except metadata.PackageNotFoundError:
        return None


def _read_pyproject_version() -> str:
    """Read version from pyproject.toml."""
    pyproject_path = _find_pyproject_path()
    if pyproject_path is None:
        raise RuntimeError(
            "Could not locate pyproject.toml and installed package metadata is unavailable."
        )

    with pyproject_path.open("rb") as handle:
        data = tomllib.load(handle)

    project = data.get("project")
    if not isinstance(project, dict):
        raise RuntimeError("[project] section is missing in pyproject.toml.")

    version = project.get("version")
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError("[project].version is missing in pyproject.toml.")

    return version.strip()


# PyInstaller extracts bundled files to a temporary directory exposed via sys._MEIPASS.
# Required to locate pyproject.toml when running as a frozen executable.
def _find_pyproject_path() -> Path | None:
    """Locate pyproject.toml for source and frozen runtime."""
    search_roots: list[Path] = []

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            search_roots.append(Path(meipass))
        search_roots.append(Path(sys.executable).resolve().parent)

    module_path = Path(__file__).resolve()
    search_roots.extend([module_path.parent, *module_path.parents])

    seen_paths: set[Path] = set()
    for root in search_roots:
        if root in seen_paths:
            continue
        seen_paths.add(root)

        candidate = root / "pyproject.toml"
        if candidate.is_file():
            return candidate

    return None
