"""Tests for MaxMind auto-update logic.

All network I/O and file I/O are mocked — no real credentials or network
access are required to run this suite.
"""

from __future__ import annotations

import io
import json
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from model.maxmind_updater import (
    MaxMindUpdater,
    _encode_basic_auth,
    _find_mmdb_member,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tar_gz(mmdb_name: str, content: bytes = b"fake-mmdb-data") -> bytes:
    """Build an in-memory tar.gz containing a single .mmdb file."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name=f"GeoLite2-City_20240101/{mmdb_name}")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def _make_updater(tmp_path: Path, interval_days: float = 7.0, on_update=None) -> MaxMindUpdater:
    return MaxMindUpdater(
        data_dir=tmp_path,
        account_id="123456",
        license_key="test_license_key",
        interval_days=interval_days,
        on_update=on_update,
    )


# ---------------------------------------------------------------------------
# Unit tests — pure logic, no I/O
# ---------------------------------------------------------------------------

class TestEncodeBasicAuth:
    def test_produces_base64_encoded_credentials(self):
        import base64
        token = _encode_basic_auth("user", "pass")
        decoded = base64.b64decode(token).decode()
        assert decoded == "user:pass"

    def test_handles_special_characters(self):
        import base64
        token = _encode_basic_auth("999", "abc/def+xyz==")
        decoded = base64.b64decode(token).decode()
        assert decoded == "999:abc/def+xyz=="


class TestFindMmdbMember:
    def test_finds_nested_mmdb(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            info = tarfile.TarInfo(name="GeoLite2-City_20240101/GeoLite2-City.mmdb")
            info.size = 4
            tar.addfile(info, io.BytesIO(b"data"))
        buf.seek(0)

        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            member = _find_mmdb_member(tar, "GeoLite2-City.mmdb")

        assert member is not None
        assert member.name.endswith("GeoLite2-City.mmdb")

    def test_returns_none_when_not_found(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            info = tarfile.TarInfo(name="README.txt")
            info.size = 3
            tar.addfile(info, io.BytesIO(b"hi!"))
        buf.seek(0)

        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            member = _find_mmdb_member(tar, "GeoLite2-City.mmdb")

        assert member is None


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

class TestStatePersistence:
    def test_read_returns_none_when_no_state_file(self, tmp_path):
        updater = _make_updater(tmp_path)
        assert updater._read_last_download() is None

    def test_write_then_read_round_trips(self, tmp_path):
        updater = _make_updater(tmp_path)
        ts = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        updater._write_last_download(ts)
        result = updater._read_last_download()
        assert result == ts

    def test_read_returns_none_on_corrupt_json(self, tmp_path):
        updater = _make_updater(tmp_path)
        (tmp_path / ".maxmind_update_state.json").write_text("not-json", encoding="utf-8")
        assert updater._read_last_download() is None

    def test_read_returns_none_on_missing_key(self, tmp_path):
        updater = _make_updater(tmp_path)
        (tmp_path / ".maxmind_update_state.json").write_text(
            json.dumps({"other_key": "value"}), encoding="utf-8"
        )
        assert updater._read_last_download() is None


# ---------------------------------------------------------------------------
# Download scheduling
# ---------------------------------------------------------------------------

class TestCheckAndMaybeDownload:
    def test_downloads_when_no_previous_state(self, tmp_path):
        updater = _make_updater(tmp_path)
        with patch.object(updater, "_download_all") as mock_dl:
            updater._check_and_maybe_download()
        mock_dl.assert_called_once()

    def test_downloads_when_interval_elapsed(self, tmp_path):
        updater = _make_updater(tmp_path, interval_days=7.0)
        old_ts = datetime.now(timezone.utc) - timedelta(days=8)
        updater._write_last_download(old_ts)

        with patch.object(updater, "_download_all") as mock_dl:
            updater._check_and_maybe_download()
        mock_dl.assert_called_once()

    def test_skips_download_when_interval_not_elapsed(self, tmp_path):
        updater = _make_updater(tmp_path, interval_days=7.0)
        recent_ts = datetime.now(timezone.utc) - timedelta(days=2)
        updater._write_last_download(recent_ts)

        with patch.object(updater, "_download_all") as mock_dl:
            updater._check_and_maybe_download()
        mock_dl.assert_not_called()

    def test_downloads_exactly_at_interval_boundary(self, tmp_path):
        updater = _make_updater(tmp_path, interval_days=7.0)
        # exactly 7 days ago (to the second)
        boundary_ts = datetime.now(timezone.utc) - timedelta(days=7, seconds=1)
        updater._write_last_download(boundary_ts)

        with patch.object(updater, "_download_all") as mock_dl:
            updater._check_and_maybe_download()
        mock_dl.assert_called_once()


# ---------------------------------------------------------------------------
# Full download flow (mocked HTTP)
# ---------------------------------------------------------------------------

def _fake_build_opener(city_bytes: bytes, asn_bytes: bytes):
    """Return a mock for urllib.request.build_opener that serves fake responses.

    build_opener is called once per _download_edition call, so each call gets
    its own opener that serves the next response in sequence.
    """
    responses = [city_bytes, asn_bytes]
    call_count = 0

    class FakeResponse:
        def __init__(self, data):
            self._data = data

        def read(self):
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    class FakeOpener:
        def open(self, req, timeout=None):
            nonlocal call_count
            resp = FakeResponse(responses[call_count % len(responses)])
            call_count += 1
            return resp

    def fake_build_opener(_handler_class):
        return FakeOpener()

    return fake_build_opener


class TestDownloadEdition:
    def test_writes_mmdb_file(self, tmp_path):
        city_content = b"city-mmdb-bytes"
        archive = _make_tar_gz("GeoLite2-City.mmdb", city_content)

        with patch("model.maxmind_updater.urllib.request.build_opener", _fake_build_opener(archive, archive)):
            updater = _make_updater(tmp_path)
            updater._download_edition("GeoLite2-City")

        dest = tmp_path / "GeoLite2-City.mmdb"
        assert dest.exists()
        assert dest.read_bytes() == city_content

    def test_raises_when_mmdb_missing_from_archive(self, tmp_path):
        # Build archive without any .mmdb inside
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            info = tarfile.TarInfo(name="README.txt")
            info.size = 2
            tar.addfile(info, io.BytesIO(b"hi"))
        archive = buf.getvalue()

        with patch("model.maxmind_updater.urllib.request.build_opener", _fake_build_opener(archive, archive)):
            updater = _make_updater(tmp_path)
            with pytest.raises(RuntimeError, match="not found inside downloaded archive"):
                updater._download_edition("GeoLite2-City")


class TestDownloadAll:
    def test_calls_on_update_after_full_success(self, tmp_path):
        city_archive = _make_tar_gz("GeoLite2-City.mmdb", b"city")
        asn_archive = _make_tar_gz("GeoLite2-ASN.mmdb", b"asn")

        on_update = MagicMock()
        updater = _make_updater(tmp_path, on_update=on_update)

        with patch("model.maxmind_updater.urllib.request.build_opener", _fake_build_opener(city_archive, asn_archive)):
            updater._download_all()

        on_update.assert_called_once()

    def test_writes_state_after_full_success(self, tmp_path):
        city_archive = _make_tar_gz("GeoLite2-City.mmdb", b"city")
        asn_archive = _make_tar_gz("GeoLite2-ASN.mmdb", b"asn")

        updater = _make_updater(tmp_path)
        with patch("model.maxmind_updater.urllib.request.build_opener", _fake_build_opener(city_archive, asn_archive)):
            updater._download_all()

        assert updater._read_last_download() is not None

    def test_skips_on_update_when_one_edition_fails(self, tmp_path):
        city_archive = _make_tar_gz("GeoLite2-City.mmdb", b"city")
        # Second response is garbage — will fail extraction
        bad_archive = b"this is not a tar file"

        on_update = MagicMock()
        updater = _make_updater(tmp_path, on_update=on_update)

        with patch("model.maxmind_updater.urllib.request.build_opener", _fake_build_opener(city_archive, bad_archive)):
            updater._download_all()

        on_update.assert_not_called()

    def test_does_not_write_state_on_partial_failure(self, tmp_path):
        city_archive = _make_tar_gz("GeoLite2-City.mmdb", b"city")
        bad_archive = b"not a tar"

        updater = _make_updater(tmp_path)
        with patch("model.maxmind_updater.urllib.request.build_opener", _fake_build_opener(city_archive, bad_archive)):
            updater._download_all()

        assert updater._read_last_download() is None


# ---------------------------------------------------------------------------
# Background thread lifecycle
# ---------------------------------------------------------------------------

class TestThreadLifecycle:
    def test_start_spawns_daemon_thread(self, tmp_path):
        updater = _make_updater(tmp_path)
        with patch.object(updater, "_run"):  # prevent actual work
            updater.start()
            assert updater._thread is not None
            assert updater._thread.daemon is True
            updater.stop()

    def test_start_is_idempotent(self, tmp_path):
        updater = _make_updater(tmp_path)
        with patch.object(updater, "_run"):
            updater.start()
            thread_1 = updater._thread
            updater.start()  # second call — should be a no-op
            assert updater._thread is thread_1
            updater.stop()

    def test_stop_sets_stop_event(self, tmp_path):
        updater = _make_updater(tmp_path)
        with patch.object(updater, "_run"):
            updater.start()
            updater.stop()
        assert updater._stop_event.is_set()


# ---------------------------------------------------------------------------
# RuntimeContext integration
# ---------------------------------------------------------------------------

class TestRuntimeIntegration:
    def test_autofetch_enabled_with_both_credentials(self, monkeypatch):
        monkeypatch.setenv("MAXMIND_ACCOUNT_ID", "12345")
        monkeypatch.setenv("MAXMIND_LICENSE_KEY", "abcdef")
        from runtime import build_runtime
        import tapmap
        ctx = build_runtime(tapmap.APP_META)
        assert ctx.maxmind_autofetch_enabled is True
        assert ctx.maxmind_account_id == "12345"
        assert ctx.maxmind_license_key == "abcdef"

    def test_autofetch_disabled_without_credentials(self, monkeypatch):
        monkeypatch.delenv("MAXMIND_ACCOUNT_ID", raising=False)
        monkeypatch.delenv("MAXMIND_LICENSE_KEY", raising=False)
        from runtime import build_runtime
        import tapmap
        ctx = build_runtime(tapmap.APP_META)
        assert ctx.maxmind_autofetch_enabled is False

    def test_custom_interval_from_env(self, monkeypatch):
        monkeypatch.setenv("MAXMIND_UPDATE_INTERVAL_DAYS", "14")
        from runtime import build_runtime
        import tapmap
        ctx = build_runtime(tapmap.APP_META)
        assert ctx.maxmind_update_interval_days == 14.0

    def test_default_interval_when_env_not_set(self, monkeypatch):
        monkeypatch.delenv("MAXMIND_UPDATE_INTERVAL_DAYS", raising=False)
        from runtime import build_runtime
        import tapmap
        from config import MAXMIND_UPDATE_INTERVAL_DAYS
        ctx = build_runtime(tapmap.APP_META)
        assert ctx.maxmind_update_interval_days == MAXMIND_UPDATE_INTERVAL_DAYS

    def test_invalid_interval_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("MAXMIND_UPDATE_INTERVAL_DAYS", "not-a-number")
        from runtime import build_runtime
        import tapmap
        from config import MAXMIND_UPDATE_INTERVAL_DAYS
        ctx = build_runtime(tapmap.APP_META)
        assert ctx.maxmind_update_interval_days == MAXMIND_UPDATE_INTERVAL_DAYS
