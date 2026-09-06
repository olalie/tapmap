"""MaxMind-specific GeoDB operations for TapMap.

Contains credential and remote/download logic specific to MaxMind GeoLite2.
"""

from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import keyring
import maxminddb
import requests


class MaxMindProvider:
    """Handle MaxMind provider-specific operations."""

    KEYRING_SERVICE = "tapmap_geolite2"
    ACCOUNT_ID_KEY = "account_id"
    LICENSE_KEY_NAME = "license_key"

    CITY_FILENAME = "GeoLite2-City.mmdb"
    ASN_FILENAME = "GeoLite2-ASN.mmdb"

    CITY_DOWNLOAD_NAME = "GeoLite2-City"
    ASN_DOWNLOAD_NAME = "GeoLite2-ASN"
    BASE_URL = "https://download.maxmind.com/app/geoip_download"

    def __init__(
        self,
        data_dir: Path,
        is_docker: bool = False,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.is_docker = is_docker

    @property
    def city_path(self) -> Path:
        """Return expected path for MaxMind City database."""
        return self.data_dir / self.CITY_FILENAME

    @property
    def asn_path(self) -> Path:
        """Return expected path for MaxMind ASN database."""
        return self.data_dir / self.ASN_FILENAME

    @property
    def credentials_path(self) -> Path:
        """Return Docker credential file path."""
        return self.data_dir / "maxmind.json"

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
    def _epoch_to_date(epoch: int | None) -> str | None:
        """Format epoch as YYYY-MM-DD in UTC."""
        if epoch is None:
            return None
        return datetime.fromtimestamp(epoch, tz=UTC).strftime("%Y-%m-%d")

    def get_local_status(self) -> dict[str, Any]:
        """Return local MaxMind pair presence/validity and version/date values."""
        city_installed = self.city_path.exists()
        asn_installed = self.asn_path.exists()

        city_epoch = self._read_build_epoch(self.city_path)
        asn_epoch = self._read_build_epoch(self.asn_path)

        city_valid = city_epoch is not None
        asn_valid = asn_epoch is not None

        city_date = self._epoch_to_date(city_epoch)
        asn_date = self._epoch_to_date(asn_epoch)

        local_version: str | None = None
        local_display_date: str | None = None
        if city_valid and asn_valid and city_epoch is not None and asn_epoch is not None:
            # For update logic, use the minimum (oldest) comparable local build key.
            local_version = self._epoch_to_date(min(city_epoch, asn_epoch))
            # For UI display, show minimum freshness across the active pair.
            local_display_date = self._epoch_to_date(min(city_epoch, asn_epoch))

        return {
            "city_installed": city_installed,
            "asn_installed": asn_installed,
            "city_valid": city_valid,
            "asn_valid": asn_valid,
            "local_version": local_version,
            "local_city_date": city_date,
            "local_asn_date": asn_date,
            "local_display_date": local_display_date,
        }

    @classmethod
    def _download_url(cls, edition_id: str, license_key: str) -> str:
        """Build MaxMind download URL for one edition."""
        # URL embeds license_key: raise request errors below with `from None`,
        # never chain them, or the key resurfaces in logged tracebacks.
        return f"{cls.BASE_URL}?edition_id={edition_id}&license_key={license_key}&suffix=tar.gz"

    def load_credentials(self) -> tuple[str, str]:
        """Load MaxMind credentials."""
        if self.is_docker:
            account_id, license_key = self.stored_credentials()

            if not account_id or not license_key:
                raise ValueError("MaxMind credentials are not configured")

            return account_id, license_key

        account_id = keyring.get_password(
            self.KEYRING_SERVICE,
            self.ACCOUNT_ID_KEY,
        )
        license_key = keyring.get_password(
            self.KEYRING_SERVICE,
            self.LICENSE_KEY_NAME,
        )

        if not account_id or not license_key:
            raise ValueError("MaxMind credentials are not configured")

        return account_id, license_key

    def credentials_exist(self) -> bool:
        """Return whether MaxMind credentials are available."""
        if self.is_docker:
            return self.credentials_path.exists()

        account_id = keyring.get_password(
            self.KEYRING_SERVICE,
            self.ACCOUNT_ID_KEY,
        )
        license_key = keyring.get_password(
            self.KEYRING_SERVICE,
            self.LICENSE_KEY_NAME,
        )

        return bool(account_id and license_key)

    def stored_credentials(self) -> tuple[str | None, str | None]:
        """Return stored MaxMind credentials without enforcing completeness."""
        if self.is_docker:
            if not self.credentials_path.exists():
                return None, None

            try:
                data = json.loads(self.credentials_path.read_text())
            except Exception:
                return None, None

            return (
                data.get("account_id"),
                data.get("license_key"),
            )

        account_id = keyring.get_password(
            self.KEYRING_SERVICE,
            self.ACCOUNT_ID_KEY,
        )
        license_key = keyring.get_password(
            self.KEYRING_SERVICE,
            self.LICENSE_KEY_NAME,
        )

        return account_id, license_key

    def register_credentials(self, account_id: str, license_key: str) -> None:
        """Persist MaxMind credentials."""
        if not account_id or not license_key:
            raise ValueError("Account ID and license key are required")

        if self.is_docker:
            data = {
                "account_id": account_id,
                "license_key": license_key,
            }

            self.credentials_path.write_text(
                json.dumps(data, indent=2),
                encoding="utf-8",
            )

            self.credentials_path.chmod(0o600)

            return

        keyring.set_password(
            self.KEYRING_SERVICE,
            self.ACCOUNT_ID_KEY,
            account_id,
        )

        keyring.set_password(
            self.KEYRING_SERVICE,
            self.LICENSE_KEY_NAME,
            license_key,
        )

    def validate_credentials(self, account_id: str, license_key: str) -> None:
        """Validate MaxMind credentials."""
        if not account_id or not license_key:
            raise ValueError("Account ID and license key are required")

        url = self._download_url(self.CITY_DOWNLOAD_NAME, license_key)

        try:
            response = requests.head(
                url,
                auth=(account_id, license_key),
                timeout=30,
                allow_redirects=True,
            )
            response.raise_for_status()

        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None

            if status == 401:
                raise ValueError("Invalid MaxMind credentials.") from None

            if status == 429:
                raise ValueError(
                    "Too many MaxMind requests. Please wait a few minutes and try again."
                ) from None

            if status == 503:
                raise ValueError("MaxMind service unavailable. Please try again later.") from None

            raise ValueError(f"MaxMind request failed (HTTP {status}).") from None

        except requests.RequestException:
            raise ValueError("Unable to contact MaxMind.") from None

    def _remote_last_modified_epoch(self, edition_id: str) -> int:
        """Return remote Last-Modified epoch for one MaxMind edition."""
        account_id, license_key = self.load_credentials()
        url = self._download_url(edition_id, license_key)

        try:
            response = requests.head(
                url,
                auth=(account_id, license_key),
                timeout=60,
                allow_redirects=True,
            )
            response.raise_for_status()
        except requests.RequestException:
            raise RuntimeError("Unable to fetch MaxMind remote version") from None

        last_modified = response.headers.get("Last-Modified")
        if last_modified is None:
            raise RuntimeError("Unable to fetch MaxMind remote version")

        try:
            return int(parsedate_to_datetime(last_modified).timestamp())
        except Exception as exc:
            raise RuntimeError("Unable to parse MaxMind remote version") from exc

    def fetch_remote_version(self) -> str:
        """Return MaxMind remote version key for update logic.

        Uses the minimum (oldest) City/ASN Last-Modified date.
        """
        city_epoch = self._remote_last_modified_epoch(self.CITY_DOWNLOAD_NAME)
        asn_epoch = self._remote_last_modified_epoch(self.ASN_DOWNLOAD_NAME)
        return self._epoch_to_date(min(city_epoch, asn_epoch))

    def _download_edition_to(self, *, edition_id: str, target_path: Path) -> Path:
        """Download one MaxMind edition and extract MMDB into target_path."""
        account_id, license_key = self.load_credentials()
        url = self._download_url(edition_id, license_key)

        try:
            response = requests.get(
                url,
                auth=(account_id, license_key),
                timeout=120,
            )
            response.raise_for_status()
        except requests.RequestException:
            raise RuntimeError("Unable to download MaxMind database") from None

        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            archive_path = temp_dir / f"{edition_id}.tar.gz"
            archive_path.write_bytes(response.content)

            with tarfile.open(archive_path, "r:gz") as archive:
                mmdb_member = next(
                    (member for member in archive.getmembers() if member.name.endswith(".mmdb")),
                    None,
                )
                if mmdb_member is None:
                    raise RuntimeError("Unable to download MaxMind database")
                archive.extract(mmdb_member, path=temp_dir, filter="data")

            extracted_path = temp_dir / mmdb_member.name
            temp_target = target_path.with_name(target_path.name + ".tmp")
            shutil.copy2(extracted_path, temp_target)
            temp_target.replace(target_path)

        return target_path

    def download_pair_to(self, target_dir: Path) -> tuple[Path, Path]:
        """Download MaxMind City/ASN databases into target_dir.

        Returns paths to downloaded City and ASN files.
        """
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)

        city_target = target / self.CITY_FILENAME
        asn_target = target / self.ASN_FILENAME

        city_path = self._download_edition_to(
            edition_id=self.CITY_DOWNLOAD_NAME,
            target_path=city_target,
        )
        asn_path = self._download_edition_to(
            edition_id=self.ASN_DOWNLOAD_NAME,
            target_path=asn_target,
        )

        return city_path, asn_path
