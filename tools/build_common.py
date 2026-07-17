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

# Paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]

SPEC_FILE = PROJECT_ROOT / "tapmap.spec"

BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"

# Temporary package staging directory.
PACKAGE_DIR = PROJECT_ROOT / "package"

# Application names
DIST_NAME = "tapmap"
EXE_NAME_WINDOWS = "tapmap.exe"

MACOS_APP_NAME = "TapMap.app"
MACOS_DMG_NAME = "TapMap.dmg"


# Helpers
def run(cmd: list[str]) -> None:
    """Run a subprocess command."""
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True)


def stop_running_app() -> None:
    """Terminate a running packaged executable on Windows."""
    if os.name != "nt":
        return

    with contextlib.suppress(Exception):
        subprocess.run(
            ["taskkill", "/F", "/IM", EXE_NAME_WINDOWS],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


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


def expected_output_file() -> Path:
    """Return the expected PyInstaller output."""
    if sys.platform == "darwin":
        return DIST_DIR / MACOS_APP_NAME

    out = DIST_DIR / DIST_NAME

    if os.name == "nt":
        out = out.with_suffix(".exe")

    return out


# Build
def clean() -> None:
    """Remove previous build artifacts."""
    stop_running_app()
    rm_tree(BUILD_DIR)
    rm_tree(DIST_DIR)
    rm_tree(PACKAGE_DIR)
    print("✓ Clean build directories")


def build_pyinstaller() -> None:
    """Run PyInstaller."""
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            str(SPEC_FILE),
        ]
    )
    print("✓ Build application")


def verify_build() -> None:
    """Verify that the expected build output exists."""
    out_file = expected_output_file()

    if not out_file.exists():
        raise FileNotFoundError(f"Expected output not found: {out_file}")

    print(f"✓ Verify build ({out_file.name})")


def require_tool(name: str) -> None:
    """Raise an error if a required tool is unavailable."""
    if shutil.which(name) is None:
        raise RuntimeError(f"Required tool '{name}' is not installed.")
