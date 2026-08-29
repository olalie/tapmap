"""Code signature inspection via macOS codesign and spctl."""

from __future__ import annotations

import re
import subprocess
from typing import Final

_SUBPROCESS_TIMEOUT_S: Final[float] = 5.0

_MACHO_MAGIC = {
    b"\xfe\xed\xfa\xce",  # 32-bit
    b"\xce\xfa\xed\xfe",  # 32-bit, byte-swapped
    b"\xfe\xed\xfa\xcf",  # 64-bit
    b"\xcf\xfa\xed\xfe",  # 64-bit, byte-swapped
    b"\xca\xfe\xba\xbe",  # universal (fat)
    b"\xbe\xba\xfe\xca",  # universal (fat), byte-swapped
}

_AUTHORITY_RE = re.compile(r"^Authority=(.+)$", re.MULTILINE)
# Team IDs are always 10 alphanumeric characters.
_SIGNER_RE = re.compile(r"^.+?: (.+) \(([A-Z0-9]{10})\)$")


def is_macho(path: str) -> bool | None:
    """Return whether path begins with a Mach-O (or universal binary) magic number.

    Returns None if the file couldn't be read at all, distinct from a
    successful read that determines it isn't a Mach-O.
    """
    try:
        with open(path, "rb") as f:
            header = f.read(4)
    except OSError:
        return None
    return header in _MACHO_MAGIC


def _parse_publisher(authority_line: str) -> str | None:
    """Parse a signer name from a codesign Authority= leaf line."""
    if authority_line == "Software Signing":
        return "Apple"
    m = _SIGNER_RE.match(authority_line)
    return m.group(1) if m else None


def _strip_path_prefix(line: str, path: str) -> str:
    """Remove a leading '<path>: ' echo from a codesign diagnostic line."""
    prefix = f"{path}: "
    return line[len(prefix) :] if line.startswith(prefix) else line


def check_signature(path: str) -> tuple[str | None, str | None, str | None]:
    """Return (state, details, publisher) for a Mach-O executable.

    state is one of "AppleSystem", "DeveloperSigned", "AppStoreSigned",
    "AdHoc", "Invalid", "Unsigned", or None on unexpected failure. details
    carries extra diagnostic text only where there is useful secondary
    information (currently only "Invalid"). publisher is the parsed signer
    name, or None. Caller is expected to have already confirmed `path` is
    a Mach-O.
    """
    try:
        display = subprocess.run(
            ["codesign", "-dvv", path],
            capture_output=True,
            text=True,
            check=False,
            timeout=_SUBPROCESS_TIMEOUT_S,
        )
    except (OSError, UnicodeDecodeError, subprocess.TimeoutExpired):
        return None, None, None

    if display.returncode != 0:
        if "code object is not signed at all" in display.stderr:
            return "Unsigned", None, None
        return None, None, None

    try:
        verify = subprocess.run(
            ["codesign", "--verify", path],
            capture_output=True,
            text=True,
            check=False,
            timeout=_SUBPROCESS_TIMEOUT_S,
        )
    except (OSError, UnicodeDecodeError, subprocess.TimeoutExpired):
        return None, None, None

    if verify.returncode != 0:
        detail = None
        if verify.stderr.strip():
            detail = _strip_path_prefix(verify.stderr.splitlines()[0], path)
        return "Invalid", detail, None

    authorities = _AUTHORITY_RE.findall(display.stderr)
    if not authorities:
        return "AdHoc", None, None

    leaf = authorities[0]
    if leaf == "Software Signing":
        state = "AppleSystem"
    elif leaf == "Apple Mac OS Application Signing":
        state = "AppStoreSigned"
    else:
        state = "DeveloperSigned"
    return state, None, _parse_publisher(leaf)


def check_notarized(path: str) -> bool:
    """Return True if spctl confirms path as Notarized Developer ID.

    Only meaningful for bundled .app processes; spctl cannot meaningfully
    assess bare executables and simply won't confirm notarization for
    them, which is treated the same as "not confirmed", not an error.
    """
    try:
        cp = subprocess.run(
            ["spctl", "-a", "-vvv", "--type", "execute", path],
            capture_output=True,
            text=True,
            check=False,
            timeout=_SUBPROCESS_TIMEOUT_S,
        )
    except (OSError, UnicodeDecodeError, subprocess.TimeoutExpired):
        return False

    return "source=Notarized Developer ID" in cp.stderr
