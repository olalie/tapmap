"""Tests for the MQTT notification channel."""

from __future__ import annotations

import logging
import ssl
import sys
from pathlib import Path
from typing import Any

import keyring
import keyring.errors
import pytest

from tapmap.app import APP_META
from tapmap.mqtt_config import MqttConfig, mqtt_config_path, save_mqtt_config
from tapmap.notifications.mqtt import MqttChannel, _build_payload, create_mqtt_channel
from tapmap.runtime import RuntimeContext


class _FakeKeyring:
    """In-memory stand-in for the keyring backend."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, key: str) -> str | None:
        return self._store.get((service, key))

    def set_password(self, service: str, key: str, value: str) -> None:
        self._store[(service, key)] = value

    def delete_password(self, service: str, key: str) -> None:
        try:
            del self._store[(service, key)]
        except KeyError:
            raise keyring.errors.PasswordDeleteError("not found") from None


@pytest.fixture
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> _FakeKeyring:
    fake = _FakeKeyring()
    monkeypatch.setattr(keyring, "get_password", fake.get_password)
    monkeypatch.setattr(keyring, "set_password", fake.set_password)
    monkeypatch.setattr(keyring, "delete_password", fake.delete_password)
    return fake


class _FakePublishInfo:
    """Stand-in for paho's MQTTMessageInfo, carrying only the .rc field send() reads."""

    def __init__(self, rc: int) -> None:
        self.rc = rc


class _FakeMqttClient:
    """Records every call a real paho Client would make, without any network I/O."""

    def __init__(self, callback_api_version: Any, protocol: Any = None, **_: Any) -> None:
        self.callback_api_version = callback_api_version
        self.protocol = protocol
        self.on_connect: Any = None
        self.on_disconnect: Any = None
        self.on_connect_fail: Any = None
        self.username: str | None = None
        self.password: str | None = None
        self.tls_set_called = False
        self.connect_async_calls: list[tuple[str, int]] = []
        self.loop_start_called = False
        self.loop_stop_called = False
        self.disconnect_called = False
        self.published: list[tuple[str, str, int, bool]] = []
        self.publish_rc = 0
        self.call_order: list[str] = []

    def username_pw_set(self, username: str | None, password: str | None = None) -> None:
        self.username = username
        self.password = password

    def tls_set(self, *args: Any, **kwargs: Any) -> None:
        self.tls_set_called = True

    def connect_async(self, host: str, port: int = 1883, **kwargs: Any) -> None:
        self.connect_async_calls.append((host, port))

    def loop_start(self) -> None:
        self.loop_start_called = True

    def loop_stop(self) -> None:
        self.loop_stop_called = True
        self.call_order.append("loop_stop")

    def disconnect(self) -> None:
        self.disconnect_called = True
        self.call_order.append("disconnect")

    def publish(
        self, topic: str, payload: str | None = None, qos: int = 0, retain: bool = False, **_: Any
    ) -> _FakePublishInfo:
        self.published.append((topic, payload, qos, retain))
        return _FakePublishInfo(self.publish_rc)


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> type[_FakeMqttClient]:
    """Replace paho's Client with the fake for the duration of the test."""
    monkeypatch.setattr("paho.mqtt.client.Client", _FakeMqttClient)
    return _FakeMqttClient


def _runtime_ctx(tmp_path: Path, *, is_docker: bool = False) -> RuntimeContext:
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
        is_docker=is_docker,
        location_override=None,
        security_extensions_dir=tmp_path,
        tray_icon_path=tmp_path / "tapmap.ico",
        notification_learning_days=7,
    )


def _config(**overrides: object) -> MqttConfig:
    values: dict[str, object] = {
        "host": "broker.local",
        "port": 1883,
        "topic": "tapmap/significant_connections",
        "tls": False,
    }
    values.update(overrides)
    return MqttConfig(**values)  # type: ignore[arg-type]


def _event(**overrides: object) -> dict[str, Any]:
    values: dict[str, object] = {
        "timestamp": "2026-09-08T12:00:00",
        "reasons": ["new_country"],
        "pid": 1234,
        "proto": "tcp",
        "ip": "8.8.8.8",
        "port": 443,
        "service": "https",
        "lat": 37.4,
        "lon": -122.1,
        "process_name": "firefox.exe",
        "exe": "C:\\Users\\ola\\firefox.exe",
        "city": "Mountain View",
        "country": "United States",
        "country_code": "US",
        "asn": 15169,
        "asn_org": "Google LLC",
        "app_name": "Firefox",
        "app_creator": None,
        "app_verification_status": None,
        "app_signature_state": None,
        "app_signature_state_details": None,
    }
    values.update(overrides)
    return values


# --- payload building ---


def test_build_payload_excludes_exe() -> None:
    payload = _build_payload(_event())
    assert "exe" not in payload


def test_build_payload_adds_hostname() -> None:
    payload = _build_payload(_event())
    assert "hostname" in payload
    assert isinstance(payload["hostname"], str)
    assert payload["hostname"]


def test_build_payload_preserves_every_other_field_unchanged() -> None:
    event = _event()
    payload = _build_payload(event)
    for key, value in event.items():
        if key == "exe":
            continue
        assert payload[key] == value


def test_build_payload_preserves_none_values() -> None:
    payload = _build_payload(_event())
    assert payload["app_verification_status"] is None
    assert payload["app_creator"] is None


# --- create_mqtt_channel: presence/availability gating ---


def test_no_mqtt_json_returns_none(tmp_path: Path) -> None:
    runtime = _runtime_ctx(tmp_path)
    assert create_mqtt_channel(runtime) is None


def test_malformed_mqtt_json_returns_none(tmp_path: Path) -> None:
    runtime = _runtime_ctx(tmp_path)
    (tmp_path / "mqtt.json").write_text("{not valid json", encoding="utf-8")
    assert create_mqtt_channel(runtime) is None


def test_paho_unavailable_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    runtime = _runtime_ctx(tmp_path)
    save_mqtt_config(mqtt_config_path(tmp_path), _config())
    monkeypatch.setitem(sys.modules, "paho.mqtt.client", None)

    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.mqtt"):
        result = create_mqtt_channel(runtime)

    assert result is None
    assert "paho-mqtt is not installed" in caplog.text


def test_keyring_failure_returns_none_and_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A missing/broken keyring backend must not prevent TapMap startup."""
    runtime = _runtime_ctx(tmp_path, is_docker=False)
    save_mqtt_config(mqtt_config_path(tmp_path), _config())

    def _raise(*args: Any, **kwargs: Any) -> None:
        raise keyring.errors.NoKeyringError("no recommended backend was available")

    monkeypatch.setattr(keyring, "get_password", _raise)

    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.mqtt"):
        result = create_mqtt_channel(runtime)  # must not raise

    assert result is None
    assert "keyring" in caplog.text.lower()


def test_keyring_failure_does_not_expose_credentials_in_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    runtime = _runtime_ctx(tmp_path, is_docker=False)
    save_mqtt_config(mqtt_config_path(tmp_path), _config())

    def _raise(*args: Any, **kwargs: Any) -> None:
        raise keyring.errors.NoKeyringError("no recommended backend was available")

    monkeypatch.setattr(keyring, "get_password", _raise)

    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.mqtt"):
        create_mqtt_channel(runtime)

    assert "secret" not in caplog.text.lower()
    assert "alice" not in caplog.text.lower()


def test_tls_setup_failure_returns_none_and_does_not_raise(
    tmp_path: Path,
    fake_client: type[_FakeMqttClient],
    fake_keyring: _FakeKeyring,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken system TLS/CA store must not prevent TapMap startup."""
    runtime = _runtime_ctx(tmp_path)
    save_mqtt_config(mqtt_config_path(tmp_path), _config(tls=True, port=8883))

    def _raise(self: _FakeMqttClient, *args: Any, **kwargs: Any) -> None:
        raise ssl.SSLError("unable to get local issuer certificate")

    monkeypatch.setattr(_FakeMqttClient, "tls_set", _raise)

    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.mqtt"):
        result = create_mqtt_channel(runtime)  # must not raise

    assert result is None
    assert "tls" in caplog.text.lower()


def test_tls_setup_failure_does_not_expose_credentials_in_logs(
    tmp_path: Path,
    fake_client: type[_FakeMqttClient],
    fake_keyring: _FakeKeyring,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime_ctx(tmp_path)
    save_mqtt_config(mqtt_config_path(tmp_path), _config(tls=True, port=8883))
    fake_keyring.set_password("tapmap_mqtt", "username", "alice")
    fake_keyring.set_password("tapmap_mqtt", "password", "secret1")

    def _raise(self: _FakeMqttClient, *args: Any, **kwargs: Any) -> None:
        raise ssl.SSLError("unable to get local issuer certificate")

    monkeypatch.setattr(_FakeMqttClient, "tls_set", _raise)

    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.mqtt"):
        create_mqtt_channel(runtime)

    assert "secret1" not in caplog.text
    assert "alice" not in caplog.text


# --- create_mqtt_channel: client construction wiring ---


def test_no_auth_no_tls_does_not_set_credentials_or_tls(
    tmp_path: Path, fake_client: type[_FakeMqttClient], fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path)
    save_mqtt_config(mqtt_config_path(tmp_path), _config())

    channel = create_mqtt_channel(runtime)

    assert channel is not None
    client = channel._client
    assert client.username is None
    assert client.tls_set_called is False
    assert client.connect_async_calls == [("broker.local", 1883)]
    assert client.loop_start_called is True


def test_on_connect_fail_is_registered(
    tmp_path: Path, fake_client: type[_FakeMqttClient], fake_keyring: _FakeKeyring
) -> None:
    """create_mqtt_channel wires on_connect_fail, so pre-CONNACK failures are logged."""
    runtime = _runtime_ctx(tmp_path)
    save_mqtt_config(mqtt_config_path(tmp_path), _config())

    channel = create_mqtt_channel(runtime)

    assert channel is not None
    assert channel._client.on_connect_fail == channel._on_connect_fail


def test_desktop_credentials_come_from_keyring(
    tmp_path: Path, fake_client: type[_FakeMqttClient], fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path, is_docker=False)
    save_mqtt_config(mqtt_config_path(tmp_path), _config())
    fake_keyring.set_password("tapmap_mqtt", "username", "alice")
    fake_keyring.set_password("tapmap_mqtt", "password", "secret1")

    channel = create_mqtt_channel(runtime)

    assert channel is not None
    assert channel._client.username == "alice"
    assert channel._client.password == "secret1"


def test_docker_credentials_come_from_config_file(
    tmp_path: Path, fake_client: type[_FakeMqttClient]
) -> None:
    runtime = _runtime_ctx(tmp_path, is_docker=True)
    save_mqtt_config(mqtt_config_path(tmp_path), _config(username="alice", password="secret1"))

    channel = create_mqtt_channel(runtime)

    assert channel is not None
    assert channel._client.username == "alice"
    assert channel._client.password == "secret1"


def test_username_without_password_is_passed_through(
    tmp_path: Path, fake_client: type[_FakeMqttClient], fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path)
    save_mqtt_config(mqtt_config_path(tmp_path), _config())
    fake_keyring.set_password("tapmap_mqtt", "username", "alice")

    channel = create_mqtt_channel(runtime)

    assert channel is not None
    assert channel._client.username == "alice"
    assert channel._client.password is None


def test_tls_enabled_calls_tls_set(
    tmp_path: Path, fake_client: type[_FakeMqttClient], fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path)
    save_mqtt_config(mqtt_config_path(tmp_path), _config(tls=True, port=8883))

    channel = create_mqtt_channel(runtime)

    assert channel is not None
    assert channel._client.tls_set_called is True
    assert channel._client.connect_async_calls == [("broker.local", 8883)]


def test_topic_from_config_is_used_by_send(
    tmp_path: Path, fake_client: type[_FakeMqttClient], fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path)
    save_mqtt_config(mqtt_config_path(tmp_path), _config(topic="custom/topic"))

    channel = create_mqtt_channel(runtime)
    assert channel is not None
    channel.send(_event())

    assert channel._client.published[0][0] == "custom/topic"


def test_send_publishes_with_qos_0_and_retain_false(
    tmp_path: Path, fake_client: type[_FakeMqttClient], fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path)
    save_mqtt_config(mqtt_config_path(tmp_path), _config())

    channel = create_mqtt_channel(runtime)
    assert channel is not None
    channel.send(_event())

    _topic, payload, qos, retain = channel._client.published[0]
    assert qos == 0
    assert retain is False
    assert isinstance(payload, str)  # published as a JSON-serialized string, not a dict


# --- send(): checking the immediate publish() result ---


def test_send_does_not_log_when_publish_succeeds_immediately(
    tmp_path: Path,
    fake_client: type[_FakeMqttClient],
    fake_keyring: _FakeKeyring,
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime = _runtime_ctx(tmp_path)
    save_mqtt_config(mqtt_config_path(tmp_path), _config())
    channel = create_mqtt_channel(runtime)
    assert channel is not None
    channel._client.publish_rc = 0  # MQTT_ERR_SUCCESS

    with caplog.at_level(logging.DEBUG, logger="tapmap.notifications.mqtt"):
        channel.send(_event())

    assert caplog.records == []


def test_send_logs_at_debug_when_publish_fails_immediately(
    tmp_path: Path,
    fake_client: type[_FakeMqttClient],
    fake_keyring: _FakeKeyring,
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime = _runtime_ctx(tmp_path)
    save_mqtt_config(mqtt_config_path(tmp_path), _config())
    channel = create_mqtt_channel(runtime)
    assert channel is not None
    channel._client.publish_rc = 4  # MQTT_ERR_NO_CONN

    with caplog.at_level(logging.DEBUG, logger="tapmap.notifications.mqtt"):
        channel.send(_event())

    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.DEBUG


def test_send_does_not_retry_or_raise_on_publish_failure(
    tmp_path: Path, fake_client: type[_FakeMqttClient], fake_keyring: _FakeKeyring
) -> None:
    """QoS 0 best-effort: a failed immediate publish is not retried or raised."""
    runtime = _runtime_ctx(tmp_path)
    save_mqtt_config(mqtt_config_path(tmp_path), _config())
    channel = create_mqtt_channel(runtime)
    assert channel is not None
    channel._client.publish_rc = 4  # MQTT_ERR_NO_CONN

    channel.send(_event())  # must not raise

    assert len(channel._client.published) == 1  # exactly one publish() call, no retry


# --- plaintext-credentials-without-TLS runtime warning ---


def test_warns_once_when_auth_configured_without_tls(
    tmp_path: Path,
    fake_client: type[_FakeMqttClient],
    fake_keyring: _FakeKeyring,
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime = _runtime_ctx(tmp_path)
    save_mqtt_config(mqtt_config_path(tmp_path), _config(tls=False))
    fake_keyring.set_password("tapmap_mqtt", "username", "alice")

    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.mqtt"):
        create_mqtt_channel(runtime)

    warnings = [r for r in caplog.records if "plaintext" in r.message]
    assert len(warnings) == 1


def test_no_warning_when_tls_enabled(
    tmp_path: Path,
    fake_client: type[_FakeMqttClient],
    fake_keyring: _FakeKeyring,
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime = _runtime_ctx(tmp_path)
    save_mqtt_config(mqtt_config_path(tmp_path), _config(tls=True, port=8883))
    fake_keyring.set_password("tapmap_mqtt", "username", "alice")

    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.mqtt"):
        create_mqtt_channel(runtime)

    assert not any("plaintext" in r.message for r in caplog.records)


def test_no_warning_when_no_auth(
    tmp_path: Path,
    fake_client: type[_FakeMqttClient],
    fake_keyring: _FakeKeyring,
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime = _runtime_ctx(tmp_path)
    save_mqtt_config(mqtt_config_path(tmp_path), _config(tls=False))

    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.mqtt"):
        create_mqtt_channel(runtime)

    assert not any("plaintext" in r.message for r in caplog.records)


# --- close/teardown ---


def test_close_stops_loop_and_disconnects(
    tmp_path: Path, fake_client: type[_FakeMqttClient], fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path)
    save_mqtt_config(mqtt_config_path(tmp_path), _config())
    channel = create_mqtt_channel(runtime)
    assert channel is not None

    channel.close()

    assert channel._client.loop_stop_called is True
    assert channel._client.disconnect_called is True


def test_close_calls_disconnect_before_loop_stop(
    tmp_path: Path, fake_client: type[_FakeMqttClient], fake_keyring: _FakeKeyring
) -> None:
    """disconnect() must run before loop_stop().

    disconnect() only queues the DISCONNECT packet; the still-running
    network thread is what actually flushes it before exiting.
    """
    runtime = _runtime_ctx(tmp_path)
    save_mqtt_config(mqtt_config_path(tmp_path), _config())
    channel = create_mqtt_channel(runtime)
    assert channel is not None

    channel.close()

    assert channel._client.call_order == ["disconnect", "loop_stop"]


# --- failure isolation through the real dispatcher ---


def test_send_failure_is_caught_by_dispatch_notification(
    tmp_path: Path, fake_client: type[_FakeMqttClient], fake_keyring: _FakeKeyring
) -> None:
    from tapmap.notifications.channel import dispatch_notification

    runtime = _runtime_ctx(tmp_path)
    save_mqtt_config(mqtt_config_path(tmp_path), _config())
    channel = create_mqtt_channel(runtime)
    assert channel is not None

    def _raise(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("broker unreachable")

    channel._client.publish = _raise  # type: ignore[assignment]

    dispatch_notification(_event(), [channel])  # must not raise


# --- MQTT lifecycle callbacks: logging and failure-repetition suppression ---


class _FakeReasonCode:
    def __init__(self, *, is_failure: bool, reason: str = "Not authorized") -> None:
        self.is_failure = is_failure
        self._reason = reason

    def __str__(self) -> str:
        return "Success" if not self.is_failure else self._reason


def _channel() -> MqttChannel:
    """A MqttChannel whose callbacks can be exercised without a real client."""
    return MqttChannel(_FakeMqttClient("v2"), "topic")


def test_on_connect_logs_info_on_success(caplog: pytest.LogCaptureFixture) -> None:
    channel = _channel()
    with caplog.at_level(logging.INFO, logger="tapmap.notifications.mqtt"):
        channel._on_connect(None, None, None, _FakeReasonCode(is_failure=False), None)

    assert any(r.levelno == logging.INFO for r in caplog.records)
    assert channel._connected is True
    assert channel._last_reported_failure is None


def test_on_connect_logs_warning_on_failure(caplog: pytest.LogCaptureFixture) -> None:
    channel = _channel()
    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.mqtt"):
        channel._on_connect(None, None, None, _FakeReasonCode(is_failure=True), None)

    assert any(r.levelno == logging.WARNING for r in caplog.records)
    assert channel._last_reported_failure is not None


def test_on_connect_repeated_identical_failure_is_suppressed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A broker that keeps rejecting the same way must not warn on every retry."""
    channel = _channel()
    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.mqtt"):
        for _ in range(5):
            channel._on_connect(None, None, None, _FakeReasonCode(is_failure=True), None)

    assert len(caplog.records) == 1


def test_on_connect_different_failure_reason_logs_again(
    caplog: pytest.LogCaptureFixture,
) -> None:
    channel = _channel()
    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.mqtt"):
        channel._on_connect(
            None, None, None, _FakeReasonCode(is_failure=True, reason="Not authorized"), None
        )
        channel._on_connect(
            None,
            None,
            None,
            _FakeReasonCode(is_failure=True, reason="Bad user name or password"),
            None,
        )

    assert len(caplog.records) == 2


def test_on_connect_failure_after_success_logs_again(caplog: pytest.LogCaptureFixture) -> None:
    """A successful connection resets failure suppression for the next episode."""
    channel = _channel()
    with caplog.at_level(logging.INFO, logger="tapmap.notifications.mqtt"):
        channel._on_connect(None, None, None, _FakeReasonCode(is_failure=True), None)
        channel._on_connect(None, None, None, _FakeReasonCode(is_failure=False), None)
        channel._on_connect(None, None, None, _FakeReasonCode(is_failure=True), None)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2


def test_on_disconnect_logs_warning_after_established_connection_drops(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failure-flagged disconnect following a live connection is a real, new failure."""
    channel = _channel()
    with caplog.at_level(logging.INFO, logger="tapmap.notifications.mqtt"):
        channel._on_connect(None, None, None, _FakeReasonCode(is_failure=False), None)
        channel._on_disconnect(None, None, None, _FakeReasonCode(is_failure=True), None)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert channel._connected is False


def test_on_disconnect_logs_info_on_normal_disconnect(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A clean, intentional disconnect (e.g. at shutdown) is not a warning."""
    channel = _channel()
    with caplog.at_level(logging.INFO, logger="tapmap.notifications.mqtt"):
        channel._on_connect(None, None, None, _FakeReasonCode(is_failure=False), None)
        channel._on_disconnect(None, None, None, _FakeReasonCode(is_failure=False), None)

    assert any(r.levelno == logging.INFO for r in caplog.records)
    assert not any(r.levelno == logging.WARNING for r in caplog.records)
    assert channel._connected is False


def test_on_disconnect_without_prior_connect_is_not_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The same-attempt echo after a rejected CONNACK is redundant and not logged."""
    channel = _channel()
    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.mqtt"):
        channel._on_disconnect(None, None, None, _FakeReasonCode(is_failure=True), None)

    assert caplog.records == []
    assert channel._last_reported_failure is None


def test_connect_failure_and_matching_disconnect_produce_one_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Reproduces the real pair for one rejected CONNACK.

    "MQTT connection failed: Not authorized" / "MQTT disconnected: Unspecified
    error". Only the meaningful first warning (from on_connect) should log.
    """
    channel = _channel()
    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.mqtt"):
        channel._on_connect(
            None, None, None, _FakeReasonCode(is_failure=True, reason="Not authorized"), None
        )
        channel._on_disconnect(
            None, None, None, _FakeReasonCode(is_failure=True, reason="Unspecified error"), None
        )

    assert len(caplog.records) == 1
    assert "Not authorized" in caplog.records[0].getMessage()


def test_repeated_connect_disconnect_failure_pairs_produce_one_warning_total(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Paho's automatic reconnect repeats the connect/disconnect pair; only the first logs."""
    channel = _channel()
    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.mqtt"):
        for _ in range(3):
            channel._on_connect(
                None, None, None, _FakeReasonCode(is_failure=True, reason="Not authorized"), None
            )
            channel._on_disconnect(
                None,
                None,
                None,
                _FakeReasonCode(is_failure=True, reason="Unspecified error"),
                None,
            )

    assert len(caplog.records) == 1


def test_on_connect_fail_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    """A pre-CONNACK failure (DNS/TCP/TLS) is logged - otherwise it is silent."""
    channel = _channel()
    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.mqtt"):
        channel._on_connect_fail(None, None)

    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING


def test_on_connect_fail_does_not_invent_a_reason(caplog: pytest.LogCaptureFixture) -> None:
    """Paho gives on_connect_fail no reason; the message must not claim one."""
    channel = _channel()
    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.mqtt"):
        channel._on_connect_fail(None, None)

    message = caplog.records[0].getMessage().lower()
    assert "tls" not in message
    assert "ssl" not in message
    assert "dns" not in message
    assert "refused" not in message


def test_on_connect_fail_repeated_is_suppressed(caplog: pytest.LogCaptureFixture) -> None:
    """A broker that stays unreachable must not warn on every automatic retry."""
    channel = _channel()
    with caplog.at_level(logging.WARNING, logger="tapmap.notifications.mqtt"):
        for _ in range(5):
            channel._on_connect_fail(None, None)

    assert len(caplog.records) == 1


def test_on_connect_fail_after_recovery_logs_again(caplog: pytest.LogCaptureFixture) -> None:
    channel = _channel()
    with caplog.at_level(logging.INFO, logger="tapmap.notifications.mqtt"):
        channel._on_connect_fail(None, None)
        channel._on_connect(None, None, None, _FakeReasonCode(is_failure=False), None)
        channel._on_connect_fail(None, None)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2


def test_mqtt_channel_is_a_notification_channel(
    tmp_path: Path, fake_client: type[_FakeMqttClient], fake_keyring: _FakeKeyring
) -> None:
    """MqttChannel satisfies the NotificationChannel protocol (has a send() method)."""
    runtime = _runtime_ctx(tmp_path)
    save_mqtt_config(mqtt_config_path(tmp_path), _config())
    channel = create_mqtt_channel(runtime)
    assert isinstance(channel, MqttChannel)
    assert callable(channel.send)
