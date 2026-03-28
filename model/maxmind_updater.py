"""Download and auto-refresh MaxMind GeoLite2 databases on a configurable schedule.

Credentials are read from the runtime context (env vars MAXMIND_ACCOUNT_ID and
MAXMIND_LICENSE_KEY).  A state file in the data directory records the last
successful download so restarts do not trigger an unnecessary re-download.

Update API:
    https://download.maxmind.com/geoip/databases/{edition}/download?suffix=tar.gz
    Basic auth: account_id : license_key
"""

from __future__ import annotations

import json
import logging
import tarfile
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

_EDITIONS: Final[list[str]] = ["GeoLite2-City", "GeoLite2-ASN"]
_BASE_URL: Final[str] = "https://download.maxmind.com/geoip/databases/{edition}/download?suffix=tar.gz"
_STATE_FILE: Final[str] = ".maxmind_update_state.json"
_CHECK_INTERVAL_S: Final[int] = 3600  # re-check once per hour whether a download is due


class MaxMindUpdater:
    """Download GeoLite2 databases on a schedule and reload GeoInfo when updated.

    Args:
        data_dir: Directory where .mmdb files are stored.
        account_id: MaxMind account ID (used as Basic-Auth username).
        license_key: MaxMind license key (used as Basic-Auth password).
        interval_days: How many days between database refreshes.
        on_update: Callable invoked after a successful download (e.g. geoinfo.reload).
    """

    def __init__(
        self,
        data_dir: Path,
        account_id: str,
        license_key: str,
        interval_days: float,
        on_update: "Callable[[], None] | None" = None,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._account_id = account_id
        self._license_key = license_key
        self._interval_s = interval_days * 86_400
        self._on_update = on_update
        self._state_path = self._data_dir / _STATE_FILE
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background update thread (daemon, safe to call once)."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="maxmind-updater",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "MaxMind auto-updater started (interval=%.1f days)", self._interval_s / 86_400
        )

    def stop(self) -> None:
        """Signal the background thread to stop and wait for it."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Check at startup and then every _CHECK_INTERVAL_S seconds."""
        self._check_and_maybe_download()

        while not self._stop_event.wait(timeout=_CHECK_INTERVAL_S):
            self._check_and_maybe_download()

    def _check_and_maybe_download(self) -> None:
        """Download databases if the update interval has elapsed."""
        last = self._read_last_download()
        if last is None:
            logger.info("MaxMind: no previous download recorded — fetching now.")
            self._download_all()
            return

        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        if elapsed >= self._interval_s:
            logger.info(
                "MaxMind: %.1f days since last download (interval=%.1f) — fetching.",
                elapsed / 86_400,
                self._interval_s / 86_400,
            )
            self._download_all()
        else:
            next_in = (self._interval_s - elapsed) / 3600
            logger.debug("MaxMind: next update in %.1f hours.", next_in)

    # ------------------------------------------------------------------
    # Download logic
    # ------------------------------------------------------------------

    def _download_all(self) -> None:
        """Attempt to download all editions; reload GeoInfo on full success."""
        success_count = 0
        for edition in _EDITIONS:
            try:
                self._download_edition(edition)
                success_count += 1
            except Exception:
                logger.exception("MaxMind: failed to download %s.", edition)

        if success_count == len(_EDITIONS):
            self._write_last_download(datetime.now(timezone.utc))
            logger.info("MaxMind: all databases updated successfully.")
            if self._on_update is not None:
                try:
                    self._on_update()
                except Exception:
                    logger.exception("MaxMind: on_update callback raised an exception.")
        elif success_count > 0:
            logger.warning(
                "MaxMind: %d/%d databases downloaded; skipping state update.",
                success_count,
                len(_EDITIONS),
            )

    def _download_edition(self, edition: str) -> None:
        """Download a single GeoLite2 edition and replace the .mmdb file in data_dir."""
        url = _BASE_URL.format(edition=edition)
        auth_token = _encode_basic_auth(self._account_id, self._license_key)

        req = urllib.request.Request(url, headers={"Authorization": f"Basic {auth_token}"})

        logger.debug("MaxMind: downloading %s from %s", edition, url)

        # MaxMind redirects to a presigned S3 URL. urllib forwards all headers
        # on redirect by default, which causes S3 to reject the request with 400
        # because it has its own auth in the query string. Strip Authorization
        # before following the redirect.
        opener = urllib.request.build_opener(_StripAuthOnRedirectHandler)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / f"{edition}.tar.gz"

            with opener.open(req, timeout=120) as resp:
                tmp_path.write_bytes(resp.read())

            mmdb_name = f"{edition}.mmdb"
            dest = self._data_dir / mmdb_name

            with tarfile.open(tmp_path, "r:gz") as tar:
                mmdb_member = _find_mmdb_member(tar, mmdb_name)
                if mmdb_member is None:
                    raise RuntimeError(
                        f"MaxMind: {mmdb_name} not found inside downloaded archive."
                    )

                tmp_dest = dest.with_suffix(".mmdb.tmp")
                with tar.extractfile(mmdb_member) as src, tmp_dest.open("wb") as out:
                    out.write(src.read())

            tmp_dest.replace(dest)
            logger.info("MaxMind: %s written to %s", mmdb_name, dest)

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _read_last_download(self) -> datetime | None:
        """Return the timestamp of the last successful download, or None."""
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            ts = data.get("last_download")
            if isinstance(ts, str):
                return datetime.fromisoformat(ts)
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            pass
        return None

    def _write_last_download(self, ts: datetime) -> None:
        """Persist the timestamp of the last successful download."""
        try:
            self._state_path.write_text(
                json.dumps({"last_download": ts.isoformat()}),
                encoding="utf-8",
            )
        except OSError:
            logger.warning("MaxMind: could not write state file %s.", self._state_path)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

class _StripAuthOnRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects without forwarding the Authorization header.

    MaxMind responds with a 302 to a presigned S3 URL. S3 returns 400 when it
    receives an Authorization header alongside its own query-string auth.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is not None:
            # Headers added via Request(headers=...) land in req.headers with
            # title-cased keys; those added via add_unredirected_header() land
            # in req.unredirected_hdrs.  Clear both to be safe.
            new_req.headers.pop("Authorization", None)
            new_req.unredirected_hdrs.pop("Authorization", None)
        return new_req


def _encode_basic_auth(account_id: str, license_key: str) -> str:
    """Return a Base64-encoded Basic-Auth credential string."""
    import base64

    credentials = f"{account_id}:{license_key}".encode("utf-8")
    return base64.b64encode(credentials).decode("ascii")


def _find_mmdb_member(
    tar: tarfile.TarFile, mmdb_name: str
) -> tarfile.TarInfo | None:
    """Return the TarInfo for the .mmdb file inside the archive, or None."""
    for member in tar.getmembers():
        if member.isfile() and member.name.endswith(mmdb_name):
            return member
    return None
