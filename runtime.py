from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path

from app_dirs import ensure_app_data_dir, ensure_native_app_data_dir
from config import SERVER_PORT


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
    server_host: str
    server_port: int
    is_docker: bool

    @property
    def geo_data_dir(self) -> Path:
        """Return the directory containing GeoIP databases."""
        return self.app_data_dir

def _get_app_data_dir(meta: AppMeta) -> Path:
    """Return application data directory for the current runtime."""
    data_dir = os.environ.get("TAPMAP_DATA_DIR")
    if data_dir:
        app_dir = Path(data_dir)
        ensure_app_data_dir(app_dir)
        return app_dir

    return ensure_native_app_data_dir(meta.name)

def _get_server_host(is_docker: bool) -> str:
    """Return server bind host for the current runtime."""
    host = os.environ.get("TAPMAP_HOST")
    if host:
        return host

    if is_docker:
        return "0.0.0.0"

    return "127.0.0.1"

def _get_server_port() -> int:
    """Return server port for the current runtime."""
    return int(os.environ.get("TAPMAP_PORT", str(SERVER_PORT)))

def _detect_docker() -> bool:
    """Return True when running in Docker."""
    return os.environ.get("TAPMAP_IN_DOCKER") == "1"

def build_runtime(meta: AppMeta) -> RuntimeContext:
    """Build the runtime context for the current OS and execution mode."""
    is_frozen = bool(getattr(sys, "frozen", False))
    run_dir = (
        Path(sys.executable).resolve().parent if is_frozen else Path(__file__).resolve().parent
    )

    app_data_dir = _get_app_data_dir(meta)
    net_backend, net_backend_version = _detect_network_backend()
    is_docker = _detect_docker()
    server_host = _get_server_host(is_docker)
    server_port = _get_server_port()

    return RuntimeContext(
        meta=meta,
        app_data_dir=app_data_dir,
        run_dir=run_dir,
        is_frozen=is_frozen,
        net_backend=net_backend,
        net_backend_version=net_backend_version,
        server_host=server_host,
        server_port=server_port,
        is_docker=is_docker,
    )

def _detect_network_backend() -> tuple[str, str]:
    """Return network backend name and version."""
    system = platform.system()

    if system in {"Windows", "Linux"}:
        import psutil

        return "psutil", getattr(psutil, "__version__", "-")

    if system == "Darwin":
        try:
            import subprocess

            result = subprocess.run(
                ["lsof", "-v"],
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return "lsof", "-"

        text = (result.stdout or "") + "\n" + (result.stderr or "")
        for line in text.splitlines():
            line_s = line.strip()
            if line_s.lower().startswith("revision:"):
                version = line_s.split(":", 1)[1].strip()
                return "lsof", version

        return "lsof", "-"

    return "unknown", "unknown"
