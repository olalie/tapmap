"""Debian package provenance inspection via dpkg and apt-cache."""

from __future__ import annotations

import subprocess
from typing import Final

_SUBPROCESS_TIMEOUT_S: Final[float] = 5.0

_GENERIC_MAINTAINERS = frozenset(
    {
        "Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>",
        "Ubuntu Core Developers <ubuntu-devel-discuss@lists.ubuntu.com>",
    }
)


def find_owning_package(real_path: str) -> str | None:
    """Return the dpkg package owning real_path, or None if unowned/unavailable."""
    try:
        result = subprocess.run(
            ["dpkg", "-S", real_path],
            capture_output=True,
            text=True,
            check=False,
            timeout=_SUBPROCESS_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout:
        return None

    package = result.stdout.splitlines()[0].split(": ", 1)[0].strip()
    return package or None


def _dpkg_verify_flagged_paths(verify_output: str) -> set[str]:
    """Return the pathnames dpkg -V reports a check failure or missing-file for.

    Parses the fixed --verify-format=rpm layout: a 9-character check string
    (or the literal "missing"), an optional "c" conffile marker, then the
    pathname, optionally followed by a parenthesized error message.
    """
    flagged = set()
    for line in verify_output.splitlines():
        tokens = line.split()
        if len(tokens) < 2:
            continue
        path_tokens = tokens[2:] if tokens[1] == "c" else tokens[1:]
        path = " ".join(path_tokens)
        if " (" in path:
            path = path.split(" (", 1)[0]
        if path:
            flagged.add(path)
    return flagged


def verify_package_integrity(package: str, real_path: str) -> bool:
    """Return True if dpkg -V finds no integrity problem for real_path specifically.

    A problem reported for a different file owned by the same package does
    not affect this result. dpkg -V's exit code does not indicate whether
    problems were found (problems are reported via stdout regardless of
    exit code); a nonzero exit means the verification itself could not be
    completed (e.g. the package can no longer be found) and is never
    treated as clean.
    """
    try:
        result = subprocess.run(
            ["dpkg", "-V", package],
            capture_output=True,
            text=True,
            check=False,
            timeout=_SUBPROCESS_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    if result.returncode != 0:
        return False

    return real_path not in _dpkg_verify_flagged_paths(result.stdout)


def _installed_version_has_repo_source(policy_output: str) -> bool:
    """Return True if apt-cache policy's installed-version block cites a repo URL."""
    lines = policy_output.splitlines()
    marker = next((i for i, line in enumerate(lines) if line.lstrip().startswith("***")), None)
    if marker is None or marker + 1 >= len(lines):
        return False

    # Source lines are indented deeper than the version markers above them; a
    # line at or below that depth starts the next version's block.
    block_indent = len(lines[marker + 1]) - len(lines[marker + 1].lstrip(" "))
    for line in lines[marker + 1 :]:
        if len(line) - len(line.lstrip(" ")) < block_indent:
            break
        if "://" in line:
            return True
    return False


def is_repo_backed(package: str) -> bool:
    """Return True if package's installed version is available from a configured APT repo."""
    try:
        result = subprocess.run(
            ["apt-cache", "policy", package],
            capture_output=True,
            text=True,
            check=False,
            timeout=_SUBPROCESS_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    return _installed_version_has_repo_source(result.stdout)


def find_creator(package: str) -> str | None:
    """Return package's Maintainer, or None if unavailable or a generic distro team."""
    try:
        result = subprocess.run(
            ["dpkg-query", "-W", "-f=${Maintainer}", package],
            capture_output=True,
            text=True,
            check=False,
            timeout=_SUBPROCESS_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None

    maintainer = result.stdout.strip()
    if not maintainer or maintainer in _GENERIC_MAINTAINERS:
        return None
    return maintainer


def _package_desktop_files(package: str) -> list[str]:
    """Return package's installed .desktop file paths under /usr/share/applications."""
    try:
        result = subprocess.run(
            ["dpkg", "-L", package],
            capture_output=True,
            text=True,
            check=False,
            timeout=_SUBPROCESS_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    return [
        line
        for line in result.stdout.splitlines()
        if line.startswith("/usr/share/applications/") and line.endswith(".desktop")
    ]


def _parse_primary_desktop_entry(desktop_path: str) -> str | None:
    """Return Name= from a .desktop file's [Desktop Entry] section, or None if NoDisplay=true."""
    try:
        with open(desktop_path, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        return None

    name = None
    in_main_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_main_section = stripped == "[Desktop Entry]"
            continue
        if not in_main_section or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key == "NoDisplay" and value.strip().lower() == "true":
            return None
        if key == "Name" and name is None:
            name = value.strip()
    return name


def find_desktop_name(package: str) -> str | None:
    """Return package's display name from its one visible .desktop entry, if unambiguous."""
    desktop_files = _package_desktop_files(package)
    displayed_names = [
        name for f in desktop_files if (name := _parse_primary_desktop_entry(f)) is not None
    ]
    return displayed_names[0] if len(displayed_names) == 1 else None
