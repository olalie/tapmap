"""Best-effort application identity and verification data for connection records.

AppInfo answers three questions about an application, regardless of platform:

    1. What is the name of the program behind this process?
    2. Who created it?
    3. Can it be verified?

It selects a platform-specific backend (see appinfo_windows.py,
appinfo_macos.py, appinfo_linux.py) that resolves an ApplicationMetadata for
one executable path, and caches results per executable path for the life of
the session. Run in best-effort mode when no backend is available for the
current OS, or backend construction fails, and return filename-derived,
unverified-looking results instead of raising.

Name/creator identity is resolved synchronously. Verification (the
per-platform expensive step) runs in a background thread pool and never
blocks lookup()/enrich(); callers see verification_status as None until it
completes.
"""

from __future__ import annotations

import logging
import os
import platform
import threading
from collections import OrderedDict
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

_DEFAULT_VERIFICATION_WORKERS = 2


class VerificationStatus(str, Enum):
    """Platform-independent verification result used internally by AppInfo.

    Windows and macOS derive the result from platform code-signing and
    verification information. Linux maps package integrity and APT repository
    information to the same internal result.
    """

    VERIFIED = "verified"
    FAILED = "failed"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class ApplicationMetadata:
    """Application identity and verification metadata resolved for one executable path.

    name is always populated. verification_status is None while background
    verification is still in progress; once set, it is final. creator is
    None only in that same window; once verification_status is set, creator
    falls back to "Unknown" if none was found. signature_state and
    signature_state_details are technical detail, independently optional.

    company_name and publisher are backend-internal inputs used only to
    compute creator; they are deliberately not part of this public contract
    since nothing else consumes them directly.
    """

    name: str
    creator: str | None
    verification_status: VerificationStatus | None
    signature_state: str | None
    signature_state_details: str | None


class AppInfoBackend(Protocol):
    """Backend interface for resolving application metadata on one OS."""

    def resolve_identity(self, exe_path: str) -> ApplicationMetadata:
        """Return the fast, synchronous portion of metadata for an executable path.

        verification_status is None when this executable also needs
        resolve_verification(); a real VerificationStatus when identity alone
        is already a complete, terminal answer (nothing further is deferred).
        """

    def resolve_verification(
        self, exe_path: str, identity: ApplicationMetadata
    ) -> ApplicationMetadata:
        """Return complete metadata after running the expensive verification step.

        Only called when resolve_identity() left verification_status as None.
        Always returns a real (non-None) verification_status.
        """


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
    """Enrich connection dictionaries with best-effort application identity and verification data.

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
        verification_workers: int = _DEFAULT_VERIFICATION_WORKERS,
    ) -> None:
        """Initialize AppInfo.

        Args:
            security_extensions_dir: Directory containing the Microsoft
                Security Extensions wrapper DLLs (Windows backend only).
            cache_size: Maximum number of executable-path results kept in memory.
            silent: When False, raise on backend construction errors.
            verification_workers: Background threads used to run the
                expensive, platform-specific verification step.
        """
        self._cache_size = max(0, int(cache_size))
        self._silent = bool(silent)
        self._cache: OrderedDict[str, ApplicationMetadata] = OrderedDict()
        self._backend = self._select_backend(security_extensions_dir)
        self._lock = threading.Lock()
        self._inflight: set[str] = set()
        self._logger = logging.getLogger(__name__)
        self._executor: ThreadPoolExecutor | None = (
            ThreadPoolExecutor(
                max_workers=max(1, int(verification_workers)),
                thread_name_prefix="tapmap-appinfo",
            )
            if self._backend is not None
            else None
        )

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
            conn["app_verification_status"] = (
                metadata.verification_status.value
                if metadata.verification_status is not None
                else None
            )
            conn["app_signature_state"] = metadata.signature_state
            conn["app_signature_state_details"] = metadata.signature_state_details

        return connections

    def lookup(self, exe_path: str) -> ApplicationMetadata:
        """Look up application metadata for an executable path.

        Returns immediately without blocking on verification. name is always
        populated; verification_status and creator may be None if verification
        for this executable hasn't completed yet.
        """
        key = os.path.normcase(exe_path)

        with self._lock:
            cached = self._cache_get(key)
            should_submit = False
            if (
                cached is not None
                and cached.verification_status is None
                and key not in self._inflight
            ):
                self._inflight.add(key)
                should_submit = True

        if cached is not None:
            if should_submit:
                self._submit_verification(key, exe_path, cached)
            return cached

        # Outside the lock: real I/O, must not block other threads' cache access.
        identity = self._resolve_identity(exe_path)

        with self._lock:
            existing = self._cache_get(key)
            if existing is not None:
                # A racing thread won the miss; use its identity, not ours.
                result = existing
            else:
                self._cache_put(key, identity)
                result = identity

            should_submit = False
            if result.verification_status is None and key not in self._inflight:
                self._inflight.add(key)
                should_submit = True

        if should_submit:
            self._submit_verification(key, exe_path, result)
        return result

    def _resolve_identity(self, exe_path: str) -> ApplicationMetadata:
        """Resolve the fast, synchronous portion of metadata for one path (uncached)."""
        if self._backend is not None:
            return self._backend.resolve_identity(exe_path)

        name = os.path.splitext(os.path.basename(exe_path))[0]
        return ApplicationMetadata(
            name=name,
            creator=_get_creator(None, None),
            verification_status=VerificationStatus.UNKNOWN,
            signature_state=None,
            signature_state_details=None,
        )

    def _submit_verification(
        self, key: str, exe_path: str, identity: ApplicationMetadata
    ) -> None:
        """Schedule the expensive verification step on the background executor.

        Caller must have already reserved `key` in self._inflight.
        """
        executor = self._executor
        try:
            if executor is None:
                raise RuntimeError("AppInfo: no executor available")
            executor.submit(self._run_verification, key, exe_path, identity)
        except RuntimeError:
            self._logger.warning(
                "AppInfo: verification executor unavailable, dropping verification for %s",
                exe_path,
            )
            with self._lock:
                self._inflight.discard(key)

    def _run_verification(
        self, key: str, exe_path: str, identity: ApplicationMetadata
    ) -> None:
        backend = self._backend
        try:
            if backend is None:
                raise RuntimeError("AppInfo: no backend available")
            result = backend.resolve_verification(exe_path, identity)
        except Exception:
            self._logger.exception("AppInfo: background verification failed for %s", exe_path)
            result = ApplicationMetadata(
                name=identity.name,
                creator=identity.creator or "Unknown",
                verification_status=VerificationStatus.UNKNOWN,
                signature_state=None,
                signature_state_details=None,
            )

        with self._lock:
            self._cache_put(key, result)
            self._inflight.discard(key)

    def resolved_for(self, exe_paths: Iterable[str]) -> dict[str, ApplicationMetadata]:
        """Return already-resolved metadata for exe_paths.

        Never triggers verification or touches LRU order. Omits exe paths
        that aren't cached or still pending. Keyed by the caller's original
        (not normcased) exe_path.
        """
        out: dict[str, ApplicationMetadata] = {}
        with self._lock:
            for exe_path in exe_paths:
                cached = self._cache.get(os.path.normcase(exe_path))
                if cached is not None and cached.verification_status is not None:
                    out[exe_path] = cached
        return out

    def close(self) -> None:
        """Stop accepting new verification work and drop anything not yet started.

        Does not wait for in-flight verification to complete. Safe to call
        more than once.
        """
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)

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
