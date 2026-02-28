"""Build TapMap (onefile) using PyInstaller.

Run from project root:
    python tools/build.py
"""

from __future__ import annotations

import contextlib
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_FILE = PROJECT_ROOT / "tapmap.spec"
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"

DIST_NAME = "tapmap"
EXE_NAME_WINDOWS = "tapmap.exe"


def run(cmd: list[str]) -> None:
    """Run a subprocess command and raise on failure."""
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True)


def stop_running_app() -> None:
    """Best effort: terminate a running packaged exe that may lock dist/ on Windows."""
    if os.name != "nt":
        return

    with contextlib.suppress(Exception):
        subprocess.run(
            ["taskkill", "/F", "/IM", EXE_NAME_WINDOWS],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _on_rm_error(func, path: str, _exc_info) -> None:
    """If a file is read-only, make it writable and retry."""
    with contextlib.suppress(Exception):
        os.chmod(path, stat.S_IWRITE)
    func(path)


def rm_tree(path: Path, *, retries: int = 12, delay_s: float = 0.25) -> None:
    """Remove a directory tree with retries (Windows locks happen)."""
    if not path.exists():
        return

    last_exc: Exception | None = None
    for _ in range(retries):
        try:
            if path.is_dir():
                shutil.rmtree(path, onerror=_on_rm_error)
            else:
                path.unlink()
            return
        except Exception as exc:
            last_exc = exc
            time.sleep(delay_s)

    if last_exc:
        raise last_exc


def expected_output_file() -> Path:
    """Return expected onefile output path."""
    out = DIST_DIR / DIST_NAME
    if os.name == "nt":
        out = out.with_suffix(".exe")
    return out


def main() -> None:
    """Build a onefile TapMap executable using PyInstaller."""
    if not SPEC_FILE.exists():
        raise FileNotFoundError(f"Spec file not found: {SPEC_FILE}")

    stop_running_app()

    rm_tree(DIST_DIR)
    rm_tree(BUILD_DIR)

    # Build from spec. Do not pass makespec-only options here.
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            str(SPEC_FILE),
        ]
    )

    out_file = expected_output_file()
    if not out_file.exists():
        raise FileNotFoundError(
            "Build finished, but expected output file was not found. "
            "Verify that tapmap.spec is configured for onefile and that name='tapmap'. "
            f"Expected: {out_file}"
        )

    print(f"Build OK. Output file: {out_file}")


if __name__ == "__main__":
    main()