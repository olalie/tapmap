"""DB-IP-specific GeoDB operations for TapMap.

Contains discovery and remote/download logic specific to DB-IP Lite.
"""

from __future__ import annotations

import gzip
import re
import shutil
from datetime import UTC, datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import maxminddb
import requests


@dataclass(frozen=True)
class _RemoteDatabaseInfo:
    """Remote DB-IP release information for one database type."""

    version: str
    download_url: str


class DbIpProvider:
    """Handle DB-IP provider-specific operations."""

    CITY_PAGE_URL = "https://db-ip.com/db/download/ip-to-city-lite"
    ASN_PAGE_URL = "https://db-ip.com/db/download/ip-to-asn-lite"

    CITY_FILENAME = "DBIP-City.mmdb"
    ASN_FILENAME = "DBIP-ASN.mmdb"

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)

    @property
    def city_path(self) -> Path:
        """Return expected path for DB-IP City database."""
        return self.data_dir / self.CITY_FILENAME

    @property
    def asn_path(self) -> Path:
        """Return expected path for DB-IP ASN database."""
        return self.data_dir / self.ASN_FILENAME

    @staticmethod
    def _read_build_epoch(path: Path) -> int | None:
        """Return build epoch from MMDB metadata, or None if unreadable."""
        if not path.exists():
            return None
        try:
            with maxminddb.open_database(path) as reader:
                build_epoch = reader.metadata().build_epoch
        except Exception:
            return None

        return int(build_epoch) if isinstance(build_epoch, int) else None

    @staticmethod
    def _epoch_to_month_key(epoch: int | None) -> str | None:
        """Format epoch as DB-IP monthly release key YYYY-MM."""
        if epoch is None:
            return None
        return datetime.fromtimestamp(epoch, tz=UTC).strftime("%Y-%m")

    @staticmethod
    def _month_key_to_display_date(month_key: str | None) -> str | None:
        """Convert monthly key YYYY-MM to UI date YYYY-MM-01."""
        if month_key is None:
            return None
        return f"{month_key}-01"

    def get_local_status(self) -> dict[str, Any]:
        """Return local DB-IP pair presence/validity and version/date values."""
        city_installed = self.city_path.exists()
        asn_installed = self.asn_path.exists()

        city_epoch = self._read_build_epoch(self.city_path)
        asn_epoch = self._read_build_epoch(self.asn_path)

        city_valid = city_epoch is not None
        asn_valid = asn_epoch is not None

        city_month = self._epoch_to_month_key(city_epoch)
        asn_month = self._epoch_to_month_key(asn_epoch)

        local_version: str | None = None
        local_display_date: str | None = None
        if city_valid and asn_valid and city_month is not None and asn_month is not None:
            # For update logic, use the minimum (oldest) monthly release key.
            local_version = min(city_month, asn_month)
            # For UI display, show minimum freshness across the active pair.
            local_display_date = self._month_key_to_display_date(local_version)

        return {
            "city_installed": city_installed,
            "asn_installed": asn_installed,
            "city_valid": city_valid,
            "asn_valid": asn_valid,
            "local_version": local_version,
            "local_city_date": self._month_key_to_display_date(city_month),
            "local_asn_date": self._month_key_to_display_date(asn_month),
            "local_display_date": local_display_date,
        }

    @staticmethod
    def _extract_latest_remote_info(page_text: str, database_name: str) -> _RemoteDatabaseInfo:
        """Extract latest DB-IP release URL and version from page HTML."""
        pattern = (
            rf"(https://download\.db-ip\.com/free/"
            rf"dbip-{database_name}-lite-(\d{{4}}-\d{{2}})\.mmdb\.gz)"
        )
        matches = re.findall(pattern, page_text)
        if not matches:
            raise RuntimeError("Unable to determine latest DB-IP Lite version")

        # Choose latest release by version key (YYYY-MM).
        latest_url, latest_version = max(matches, key=lambda m: m[1])
        return _RemoteDatabaseInfo(version=latest_version, download_url=latest_url)

    def _get_remote_info(self, page_url: str, database_name: str) -> _RemoteDatabaseInfo:
        """Fetch and parse remote DB-IP release info for one database."""
        try:
            response = requests.get(page_url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError("Unable to determine latest DB-IP Lite version") from exc

        return self._extract_latest_remote_info(response.text, database_name)

    def fetch_remote_version(self) -> str:
        """Return DB-IP remote version key for update logic.

        Uses the minimum (oldest) City/ASN monthly version key.
        """
        city = self._get_remote_info(self.CITY_PAGE_URL, "city")
        asn = self._get_remote_info(self.ASN_PAGE_URL, "asn")
        return min(city.version, asn.version)

    @staticmethod
    def _download_and_extract_gz(download_url: str, target_path: Path) -> Path:
        """Download a .mmdb.gz file and extract it to target_path."""
        try:
            response = requests.get(download_url, timeout=120)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError("Unable to download DB-IP database") from exc

        gz_path = target_path.with_suffix(".mmdb.gz")
        gz_path.write_bytes(response.content)

        temp_target = target_path.with_name(target_path.name + ".tmp")
        with gzip.open(gz_path, "rb") as source:
            with open(temp_target, "wb") as destination:
                shutil.copyfileobj(source, destination)

        temp_target.replace(target_path)
        gz_path.unlink(missing_ok=True)
        return target_path

    def download_pair_to(self, target_dir: Path) -> tuple[Path, Path]:
        """Download DB-IP City/ASN databases into target_dir.

        Returns paths to downloaded City and ASN files.
        """
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)

        city_info = self._get_remote_info(self.CITY_PAGE_URL, "city")
        asn_info = self._get_remote_info(self.ASN_PAGE_URL, "asn")

        city_target = target / self.CITY_FILENAME
        asn_target = target / self.ASN_FILENAME

        city_path = self._download_and_extract_gz(city_info.download_url, city_target)
        asn_path = self._download_and_extract_gz(asn_info.download_url, asn_target)

        return city_path, asn_path
