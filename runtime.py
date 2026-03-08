from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app_dirs import get_or_create_app_data_dir


@dataclass(frozen=True)
class AppMeta:
    """Define application metadata."""

    name: str
    version: str
    author: str


@dataclass(frozen=True)
class RuntimeContext:
    """Define runtime context for the current OS and execution mode.

    Attributes:
        meta: Application metadata.
        app_data_dir: Per-user application data directory.
        run_dir: Directory containing the executable or source entry point.
        is_frozen: True when running as a bundled executable (PyInstaller).
        net_backend: Network connection backend name.
        net_backend_version: Network backend version.
    """

    meta: AppMeta
    app_data_dir: Path
    run_dir: Path
    is_frozen: bool
    net_backend: str
    net_backend_version: str

    @property
    def geo_data_dir(self) -> Path:
        """Return the directory containing GeoIP databases."""
        return self.app_data_dir


def build_runtime(meta: AppMeta) -> RuntimeContext:
    """Build the runtime context for the current OS and execution mode."""
    is_frozen = bool(getattr(sys, "frozen", False))
    run_dir = (
        Path(sys.executable).resolve().parent if is_frozen else Path(__file__).resolve().parent
    )
    app_data_dir = get_or_create_app_data_dir(meta.name)
    net_backend, net_backend_version = _detect_network_backend()

    return RuntimeContext(
        meta=meta,
        app_data_dir=app_data_dir,
        run_dir=run_dir,
        is_frozen=is_frozen,
        net_backend=net_backend,
        net_backend_version=net_backend_version,
    )


def _detect_network_backend() -> tuple[str, str]:
    """Return network backend name and version."""
    system = platform.system()

    if system == "Windows":
        import psutil

        return "psutil", getattr(psutil, "__version__", "-")

    if system == "Linux":
        if not shutil.which("ss"):
            return "ss", "not found"

        p = subprocess.run(["ss", "-V"], capture_output=True, text=True, check=False)
        text = (p.stdout + p.stderr).strip()
        m = re.search(r"\biproute2-([0-9][0-9A-Za-z.\-+]*)\b", text)
        return "ss", (f"iproute2 {m.group(1)}" if m else "unknown")

    return "unknown", "unknown"
