"""Best-effort application identity and trust data for connection records.

AppInfo answers three questions about an application, regardless of platform:

    1. What is the name of the program behind this process?
    2. Who created it?
    3. Can it be trusted?

It selects a platform-specific backend (see appinfo_windows.py,
appinfo_macos.py, appinfo_linux.py) that resolves an ApplicationMetadata for
one executable path, and caches results per executable path for the life of
the session. Run in best-effort mode when no backend is available for the
current OS, or backend construction fails, and return filename-derived,
untrusted-looking results instead of raising.
"""

from __future__ import annotations

import os
import platform
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class TrustVerdict(str, Enum):
    """Coarse, UI-stable trust verdict for an executable.

    Unsigned is treated as NOT_TRUSTED (a definitive answer from the signature
    check); UNKNOWN is reserved for cases where the check itself could not
    run at all (disabled, or an unexpected failure).
    """

    TRUSTED = "trusted"
    NOT_TRUSTED = "not_trusted"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ApplicationMetadata:
    """Application identity and trust metadata resolved for one executable path.

    name, creator and trust are always populated - UNKNOWN/"Unknown" are
    themselves valid answers, never absent. signature_state and
    signature_state_details are technical detail and may be None.

    company_name and publisher are backend-internal inputs used only to
    compute creator; they are deliberately not part of this public contract
    since nothing else consumes them directly.
    """

    name: str
    creator: str
    trust: TrustVerdict
    signature_state: str | None
    signature_state_details: str | None


class AppInfoBackend(Protocol):
    """Backend interface for resolving application metadata on one OS."""

    def resolve(self, exe_path: str) -> ApplicationMetadata:
        """Return application metadata for an executable path."""


def _get_creator(company_name: str | None, publisher: str | None) -> str:
    """Return the best answer to "who created this program?".

    Preference:
      1. CompanyName (VERSIONINFO) - identifies the software vendor.
      2. Publisher (signing certificate) - identifies the signer, which is
         not always the vendor (e.g. Intel drivers signed by "Microsoft
         Windows Hardware Compatibility Publisher").
      3. "Unknown"

    Platform-independent: takes whatever backend-specific sources resolved
    to these two opaque identity strings, without assuming their origin.
    """
    return company_name or publisher or "Unknown"


class AppInfo:
    """Enrich connection dictionaries with best-effort application identity and trust data.

    Run without a backend selected (unsupported OS, or backend construction
    fails) in disabled mode, and cache lookups per executable path for the
    life of the session.
    """

    def __init__(
        self,
        security_extensions_dir: Path,
        *,
        cache_size: int = 2_000,
        silent: bool = True,
    ) -> None:
        """Initialize AppInfo.

        Args:
            security_extensions_dir: Directory containing the Microsoft
                Security Extensions wrapper DLLs (Windows backend only).
            cache_size: Maximum number of executable-path results kept in memory.
            silent: When False, raise on backend construction errors.
        """
        self._cache_size = max(0, int(cache_size))
        self._silent = bool(silent)
        self._cache: OrderedDict[str, ApplicationMetadata] = OrderedDict()
        self._backend = self._select_backend(security_extensions_dir)

    @property
    def enabled(self) -> bool:
        """Return True if a platform backend is available."""
        return self._backend is not None

    def _select_backend(self, security_extensions_dir: Path) -> AppInfoBackend | None:
        """Select and construct the backend for the current OS.

        Returns:
            None when no backend exists for this OS, or backend construction
            failed and silent is True.
        """
        system = platform.system()

        try:
            if system == "Windows":
                from .appinfo_windows import WindowsAppInfoBackend

                return WindowsAppInfoBackend(security_extensions_dir)

            if system == "Darwin":
                from .appinfo_macos import MacOSAppInfoBackend

                return MacOSAppInfoBackend()

            if system == "Linux":
                from .appinfo_linux import LinuxAppInfoBackend

                return LinuxAppInfoBackend()
        except Exception:
            if not self._silent:
                raise

        return None

    def enrich(self, connections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Enrich connection dictionaries in-place using exe.

        Args:
            connections: List of connection dicts.

        Returns:
            The same list object, enriched in-place.
        """
        if not isinstance(connections, list) or not connections:
            return connections

        for conn in connections:
            if not isinstance(conn, dict):
                continue

            exe = conn.get("exe")
            if not isinstance(exe, str) or not exe:
                continue

            metadata = self.lookup(exe)
            conn["app_name"] = metadata.name
            conn["app_creator"] = metadata.creator
            conn["app_trust"] = metadata.trust.value
            conn["app_signature_state"] = metadata.signature_state
            conn["app_signature_state_details"] = metadata.signature_state_details

        return connections

    def lookup(self, exe_path: str) -> ApplicationMetadata:
        """Look up application metadata for an executable path.

        Returns:
            ApplicationMetadata; name/creator/trust are never absent, even
            when disabled or on lookup failure.
        """
        key = os.path.normcase(exe_path)

        cached = self._cache_get(key)
        if cached is not None:
            return cached

        metadata = self._resolve(exe_path)
        self._cache_put(key, metadata)
        return metadata

    def _resolve(self, exe_path: str) -> ApplicationMetadata:
        """Resolve application metadata for one executable path (uncached)."""
        if self._backend is not None:
            return self._backend.resolve(exe_path)

        name = os.path.splitext(os.path.basename(exe_path))[0]
        return ApplicationMetadata(
            name=name,
            creator=_get_creator(None, None),
            trust=TrustVerdict.UNKNOWN,
            signature_state=None,
            signature_state_details=None,
        )

    def _cache_get(self, key: str) -> ApplicationMetadata | None:
        """Return cached value and refresh LRU order."""
        if self._cache_size <= 0:
            return None
        val = self._cache.get(key)
        if val is None:
            return None
        self._cache.move_to_end(key, last=True)
        return val

    def _cache_put(self, key: str, metadata: ApplicationMetadata) -> None:
        """Insert into cache and evict least-recently-used items if needed."""
        if self._cache_size <= 0:
            return
        self._cache[key] = metadata
        self._cache.move_to_end(key, last=True)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
