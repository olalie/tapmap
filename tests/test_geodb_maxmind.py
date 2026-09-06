"""Regression tests for MaxMind license key exposure in errors and logs."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

import pytest
import requests

from tapmap.app import APP_META
from tapmap.geodb.maxmind import MaxMindProvider
from tapmap.geodb.service import GeoDbService
from tapmap.runtime import RuntimeContext

LICENSE_KEY = "supersecretlicensekey123"
ACCOUNT_ID = "12345"


def _http_error(status_code: int, url: str) -> requests.HTTPError:
    """Build an HTTPError the way requests.Response.raise_for_status() would."""
    response = requests.Response()
    response.status_code = status_code
    response.url = url
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        return exc
    raise AssertionError("status_code did not trigger raise_for_status")


def _leaking_url(provider: MaxMindProvider, edition_id: str) -> str:
    """Return a MaxMind download URL containing the license key."""
    return provider._download_url(edition_id, LICENSE_KEY)


def _assert_license_key_absent(exc: BaseException) -> None:
    """Assert the license key is absent from exc's message and formatted traceback."""
    assert LICENSE_KEY not in str(exc)

    # Same rendering logger.exception() uses: proves the key can't reach tapmap.log.
    formatted = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    assert LICENSE_KEY not in formatted


def _runtime_ctx(tmp_path: Path) -> RuntimeContext:
    """Build a minimal runtime context for GeoDbService construction."""
    return RuntimeContext(
        meta=APP_META,
        app_data_dir=tmp_path,
        run_dir=tmp_path,
        is_frozen=False,
        net_backend="psutil",
        net_backend_version="test",
        server_host="127.0.0.1",
        server_port=8050,
        launch_browser=True,
        cache_retention_min=0,
        is_docker=False,
        location_override=None,
        security_extensions_dir=tmp_path,
        tray_icon_path=tmp_path / "tapmap.ico",
    )


class TestValidateCredentials:
    @pytest.mark.parametrize(
        ("status_code", "expected_message"),
        [
            (401, "Invalid MaxMind credentials."),
            (500, "MaxMind request failed (HTTP 500)."),
        ],
    )
    def test_http_error_does_not_leak_license_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        status_code: int,
        expected_message: str,
    ) -> None:
        """HTTPError branches keep their public message but drop the raw request error."""
        provider = MaxMindProvider(tmp_path)
        url = _leaking_url(provider, provider.CITY_DOWNLOAD_NAME)

        def fake_head(*_args: Any, **_kwargs: Any) -> Any:
            raise _http_error(status_code, url)

        monkeypatch.setattr(requests, "head", fake_head)

        with pytest.raises(ValueError) as exc_info:
            provider.validate_credentials(ACCOUNT_ID, LICENSE_KEY)

        assert str(exc_info.value) == expected_message
        _assert_license_key_absent(exc_info.value)

    def test_connection_error_does_not_leak_license_key(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """requests.ConnectionError has no response; this except clause must also drop it."""
        provider = MaxMindProvider(tmp_path)
        url = _leaking_url(provider, provider.CITY_DOWNLOAD_NAME)
        message = (
            f"HTTPSConnectionPool(host='download.maxmind.com', port=443): "
            f"Max retries exceeded with url: {url}"
        )

        def fake_head(*_args: Any, **_kwargs: Any) -> Any:
            raise requests.ConnectionError(message)

        monkeypatch.setattr(requests, "head", fake_head)

        with pytest.raises(ValueError) as exc_info:
            provider.validate_credentials(ACCOUNT_ID, LICENSE_KEY)

        assert str(exc_info.value) == "Unable to contact MaxMind."
        _assert_license_key_absent(exc_info.value)


class TestFetchRemoteVersion:
    def test_head_failure_does_not_leak_license_key(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A failed remote-version check must not chain the raw request error."""
        provider = MaxMindProvider(tmp_path)
        monkeypatch.setattr(provider, "load_credentials", lambda: (ACCOUNT_ID, LICENSE_KEY))
        url = _leaking_url(provider, provider.CITY_DOWNLOAD_NAME)

        def fake_head(*_args: Any, **_kwargs: Any) -> Any:
            raise _http_error(503, url)

        monkeypatch.setattr(requests, "head", fake_head)

        with pytest.raises(RuntimeError) as exc_info:
            provider.fetch_remote_version()

        assert str(exc_info.value) == "Unable to fetch MaxMind remote version"
        _assert_license_key_absent(exc_info.value)


class TestDownloadPair:
    def test_download_failure_does_not_leak_license_key(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A failed database download must not chain the raw request error."""
        provider = MaxMindProvider(tmp_path)
        monkeypatch.setattr(provider, "load_credentials", lambda: (ACCOUNT_ID, LICENSE_KEY))
        url = _leaking_url(provider, provider.CITY_DOWNLOAD_NAME)

        def fake_get(*_args: Any, **_kwargs: Any) -> Any:
            raise _http_error(429, url)

        monkeypatch.setattr(requests, "get", fake_get)

        with pytest.raises(RuntimeError) as exc_info:
            provider.download_pair_to(tmp_path / "staged")

        assert str(exc_info.value) == "Unable to download MaxMind database"
        _assert_license_key_absent(exc_info.value)

    def test_install_failure_not_logged_with_license_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """GeoDbService.install() must log a failed MaxMind download without the license key."""
        service = GeoDbService(_runtime_ctx(tmp_path))
        monkeypatch.setattr(
            service.maxmind, "load_credentials", lambda: (ACCOUNT_ID, LICENSE_KEY)
        )
        url = _leaking_url(service.maxmind, service.maxmind.CITY_DOWNLOAD_NAME)

        def fake_get(*_args: Any, **_kwargs: Any) -> Any:
            raise _http_error(500, url)

        monkeypatch.setattr(requests, "get", fake_get)

        with caplog.at_level("ERROR", logger="tapmap.geodb.service"):
            response = service.install("maxmind")

        assert response["error"] == "download_failed"
        assert LICENSE_KEY not in caplog.text
