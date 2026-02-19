"""Build TapMap using PyInstaller.

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

APP_NAME = "TapMap"
SPEC_FILE = Path("tapmap.spec")
DIST_DIR = Path("dist")
BUILD_DIR = Path("build")


def run(cmd: list[str]) -> None:
    """Run a subprocess command and raise on failure."""
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True)


def stop_running_app(app_name: str) -> None:
    """Best effort: terminate a running packaged exe that may lock dist/."""
    exe_name = f"{app_name}.exe"
    with contextlib.suppress(Exception):
        subprocess.run(
            ["taskkill", "/F", "/IM", exe_name],
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
    if not path.exists() or not path.is_dir():
        return

    last_exc: Exception | None = None
    for _ in range(retries):
        try:
            shutil.rmtree(path, onerror=_on_rm_error)
            return
        except Exception as exc:
            last_exc = exc
            time.sleep(delay_s)

    if last_exc:
        raise last_exc


def main() -> None:
    """Build a packaged TapMap executable using PyInstaller."""
    # Stop a running exe that may lock dist/ files.
    stop_running_app(APP_NAME)

    # Clean output folders.
    rm_tree(DIST_DIR)
    rm_tree(BUILD_DIR)

    # Build (onedir is default, spec controls config).
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC_FILE)])

    # Post-build: ensure external data folder exists next to exe.
    app_dir = DIST_DIR / APP_NAME
    data_dir = app_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    readme = data_dir / "README.txt"
    if not readme.exists():
        readme.write_text(
            "Place GeoIP .mmdb databases here.\n"
            "Required files:\n"
            "- GeoLite2-ASN.mmdb\n"
            "- GeoLite2-City.mmdb\n",
            encoding="utf-8",
        )

    print(f"Build OK. Data folder ensured at: {data_dir}")


if __name__ == "__main__":
    main()
