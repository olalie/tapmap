"""Shared helper functions for the build system."""

from __future__ import annotations

import contextlib
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import tomllib

# Paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_FILE = PROJECT_ROOT / "tapmap.spec"
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"

# Temporary staging area used by platform-specific packaging.
PACKAGE_DIR = PROJECT_ROOT / "package"

# Signing identity for macOS builds. This is cached after the first lookup.
SIGNING_IDENTITY: str | None = None


# Process helpers
def run(
    cmd: list[str],
    *,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command."""
    print(">", " ".join(cmd), flush=True)

    result = subprocess.run(
        cmd,
        check=False,
        text=True,
        capture_output=capture_output,
    )

    if result.returncode:
        if capture_output:
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)

        raise subprocess.CalledProcessError(
            result.returncode,
            result.args,
            output=result.stdout,
            stderr=result.stderr,
        )

    return result


def require_tool(name: str) -> None:
    """Raise an error if a required tool is unavailable."""
    if shutil.which(name) is None:
        raise RuntimeError(f"Required tool '{name}' is not installed.")


# File helpers
def _on_rm_error(func, path: str, _exc) -> None:
    """Retry removal of read-only files."""
    with contextlib.suppress(Exception):
        os.chmod(path, stat.S_IWRITE)
    func(path)


def rm_tree(path: Path, *, retries: int = 12, delay_s: float = 0.25) -> None:
    """Remove a file or directory tree."""
    if not path.exists():
        return

    last_exc: Exception | None = None

    for _ in range(retries):
        try:
            if path.is_dir():
                shutil.rmtree(path, onexc=_on_rm_error)
            else:
                path.unlink()
            return
        except Exception as exc:
            last_exc = exc
            time.sleep(delay_s)

    if last_exc:
        raise last_exc


# Project helpers
def project_metadata() -> dict:
    """Return project metadata from pyproject.toml."""
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]


# Common build steps
def run_tests() -> None:
    """Run automated tests."""
    _ = run(
        [sys.executable, "-m", "pytest", "-qq"],
        capture_output=True,
    )

    print("✓ Tests passed")


def build_application() -> None:
    """Build the application using PyInstaller."""
    _ = run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "--log-level=WARN",
            str(SPEC_FILE),
        ],
        capture_output=True,
    )

    print("✓ Build application")


# macOS helpers
def get_signing_identity() -> str | None:
    """Return the Developer ID Application signing identity."""
    global SIGNING_IDENTITY

    if SIGNING_IDENTITY is not None:
        return SIGNING_IDENTITY

    result = subprocess.run(
        [
            "security",
            "find-identity",
            "-v",
            "-p",
            "codesigning",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    for line in result.stdout.splitlines():
        if "Developer ID Application:" not in line:
            continue

        first = line.find('"')
        last = line.rfind('"')

        if first != -1 and last > first:
            SIGNING_IDENTITY = line[first + 1 : last]
            return SIGNING_IDENTITY

    return None
