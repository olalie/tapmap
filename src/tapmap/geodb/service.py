"""GeoDB orchestration service for TapMap.

The service layer coordinates provider-specific operations and exposes a small
API suitable for callback orchestration in app.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, TypedDict

from .dbip import DbIpProvider
from .maxmind import MaxMindProvider


class GeoDbStatus(TypedDict):
    """Service payload contract for GeoDB status used by callbacks."""

    provider: Literal["maxmind", "dbip", "none"]
    city_installed: bool
    asn_installed: bool
    city_valid: bool
    asn_valid: bool
    local_version: str | None
    local_city_date: str | None
    local_asn_date: str | None
    local_display_date: str | None
    remote_version: str | None
    update_available: Literal["yes", "no", "unknown"]
    busy: bool
    message: str
    error: str | None


class GeoDbService:
    """Coordinate local GeoDB status and provider operations.

    This class is intentionally minimal in Step 1. Operational methods are
    added in later implementation steps.
    """

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.maxmind = MaxMindProvider(data_dir=self.data_dir)
        self.dbip = DbIpProvider(data_dir=self.data_dir)
        self._busy = False

    @staticmethod
    def _empty_status(message: str) -> GeoDbStatus:
        """Return default status for no active provider."""
        return {
            "provider": "none",
            "city_installed": False,
            "asn_installed": False,
            "city_valid": False,
            "asn_valid": False,
            "local_version": None,
            "local_city_date": None,
            "local_asn_date": None,
            "local_display_date": None,
            "remote_version": None,
            "update_available": "unknown",
            "busy": False,
            "message": message,
            "error": None,
        }

    def _build_active_status(
        self,
        provider: Literal["maxmind", "dbip"],
        local: dict[str, Any],
        message: str,
    ) -> GeoDbStatus:
        """Build active-provider status payload with stable keys."""
        return {
            "provider": provider,
            "city_installed": bool(local.get("city_installed", False)),
            "asn_installed": bool(local.get("asn_installed", False)),
            "city_valid": bool(local.get("city_valid", False)),
            "asn_valid": bool(local.get("asn_valid", False)),
            "local_version": local.get("local_version"),
            "local_city_date": local.get("local_city_date"),
            "local_asn_date": local.get("local_asn_date"),
            "local_display_date": local.get("local_display_date"),
            "remote_version": None,
            "update_available": "unknown",
            "busy": self._busy,
            "message": message,
            "error": None,
        }

    @staticmethod
    def _pair_is_valid(local: dict[str, Any]) -> bool:
        """Return True when both City and ASN files are valid MMDB files."""
        return bool(local.get("city_valid", False) and local.get("asn_valid", False))

    def local_status(self) -> GeoDbStatus:
        """Return the current local provider status from disk.

        Active-provider semantics:
        - Prefer MaxMind when both providers are valid.
        - Otherwise use DB-IP when valid.
        - Otherwise provider is none.
        The installed/valid/date/version fields describe only the active
        provider, not all provider files present on disk.
        """
        maxmind_local = self.maxmind.get_local_status()
        dbip_local = self.dbip.get_local_status()

        if self._pair_is_valid(maxmind_local):
            return self._build_active_status(
                provider="maxmind",
                local=maxmind_local,
                message="MaxMind GeoLite2 databases detected",
            )

        if self._pair_is_valid(dbip_local):
            return self._build_active_status(
                provider="dbip",
                local=dbip_local,
                message="DB-IP Lite databases detected",
            )

        status = self._empty_status("No valid GeoIP provider databases detected")
        status["busy"] = self._busy
        return status

    def recheck(self) -> GeoDbStatus:
        """Re-evaluate local database status.

        In Step 2 this is equivalent to local status recalculation.
        """
        return self.local_status()

    def install(self, provider: str) -> GeoDbStatus:
        """Install provider databases.

        Placeholder in Step 1; implemented in later steps.
        """
        raise NotImplementedError("GeoDB install is not implemented yet")

    def update(self) -> GeoDbStatus:
        """Update currently detected provider databases.

        Placeholder in Step 1; implemented in later steps.
        """
        raise NotImplementedError("GeoDB update is not implemented yet")

    @staticmethod
    def _is_remote_newer(provider: str, local_version: str, remote_version: str) -> bool:
        """Return True when remote version is newer than local version."""
        if provider == "maxmind":
            try:
                return int(remote_version) > int(local_version)
            except (TypeError, ValueError):
                return False
        if provider == "dbip":
            # DB-IP monthly keys are YYYY-MM and compare lexicographically.
            return remote_version > local_version
        return False

    def check_updates(self) -> GeoDbStatus:
        """Check remote update availability for active provider.

        Credentials and provider internals are never included in the returned
        status payload.
        """
        if self._busy:
            status = self.local_status()
            status["message"] = "Another GeoDB operation is already running"
            status["error"] = "busy"
            return status

        self._busy = True
        try:
            status = self.local_status()
            status["busy"] = True

            provider = status["provider"]
            local_version = status["local_version"]

            if provider == "none":
                status["message"] = "No active provider available for update check"
                status["update_available"] = "unknown"
                return status

            if not isinstance(local_version, str) or not local_version:
                status["message"] = "Unable to determine local provider version"
                status["update_available"] = "unknown"
                return status

            try:
                if provider == "maxmind":
                    remote_version = self.maxmind.fetch_remote_version()
                else:
                    remote_version = self.dbip.fetch_remote_version()
            except Exception:
                status["message"] = "Unable to check for database updates"
                status["error"] = "remote_check_failed"
                status["update_available"] = "unknown"
                return status

            status["remote_version"] = remote_version
            status["update_available"] = (
                "yes"
                if self._is_remote_newer(provider, local_version, remote_version)
                else "no"
            )
            status["message"] = "Update check completed"
            return status
        finally:
            self._busy = False
