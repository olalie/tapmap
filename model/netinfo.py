from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ProcessInfo:
    """Store process metadata for a socket record."""

    status: str
    label: str
    name: str | None = None
    exe: str | None = None
    cmdline: list[str] | None = None


class NetInfoBackend(Protocol):
    """Backend interface for collecting socket records."""

    def get_data(self) -> list[dict[str, Any]]:
        """Return connection records with socket and process fields."""


class NetInfo:
    """Facade that selects the correct backend for the current OS.

    Args:
        allowed_statuses:
            If set, include only TCP connections with a status in this set.
            Always include UDP sockets.
    """

    def __init__(self, allowed_statuses: set[str] | None = None) -> None:
        self.allowed_statuses = allowed_statuses
        self._backend = self._select_backend()

    def get_data(self) -> list[dict[str, Any]]:
        """Return connection records with socket and process fields."""
        return self._backend.get_data()

    def _select_backend(self) -> NetInfoBackend:
        system = platform.system()

        if system == "Linux":
            from .netinfo_linux import LinuxNetInfo

            return LinuxNetInfo(allowed_statuses=self.allowed_statuses)

        if system == "Windows":
            from .netinfo_windows import WindowsNetInfo

            return WindowsNetInfo(allowed_statuses=self.allowed_statuses)

        raise NotImplementedError(f"NetInfo backend is not implemented for OS: {system}")
