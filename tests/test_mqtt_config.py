"""Tests for MQTT configuration and credential persistence."""

from __future__ import annotations

import json
from pathlib import Path

import keyring
import keyring.errors
import pytest

from tapmap.mqtt_config import (
    KEYRING_SERVICE,
    MqttConfig,
    clear_credentials,
    delete_mqtt_config,
    get_stored_credentials,
    load_mqtt_config,
    mqtt_config_path,
    save_mqtt_config,
    set_credentials,
)


class _FakeKeyring:
    """In-memory stand-in for the keyring backend, keyed like the real API."""

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
    """Replace the keyring module's functions with an in-memory fake."""
    fake = _FakeKeyring()
    monkeypatch.setattr(keyring, "get_password", fake.get_password)
    monkeypatch.setattr(keyring, "set_password", fake.set_password)
    monkeypatch.setattr(keyring, "delete_password", fake.delete_password)
    return fake


def _config(**overrides: object) -> MqttConfig:
    values: dict[str, object] = {
        "host": "192.168.1.50",
        "port": 1883,
        "topic": "tapmap/significant_connections",
        "tls": False,
    }
    values.update(overrides)
    return MqttConfig(**values)  # type: ignore[arg-type]


# --- mqtt_config_path ---


def test_mqtt_config_path_is_under_app_data_dir(tmp_path: Path) -> None:
    assert mqtt_config_path(tmp_path) == tmp_path / "mqtt.json"


# --- load/save/delete round-trip ---


def test_missing_file_returns_none(tmp_path: Path) -> None:
    assert load_mqtt_config(tmp_path / "mqtt.json") is None


def test_round_trip_desktop_shape(tmp_path: Path) -> None:
    """A config with no credentials round-trips exactly."""
    path = tmp_path / "mqtt.json"
    config = _config(host="mqtt.example.com", port=8883, tls=True)

    save_mqtt_config(path, config)
    loaded = load_mqtt_config(path)

    assert loaded == config


def test_round_trip_docker_shape_with_credentials(tmp_path: Path) -> None:
    """A config with embedded credentials (the Docker shape) round-trips exactly."""
    path = tmp_path / "mqtt.json"
    config = _config(username="alice", password="secret")

    save_mqtt_config(path, config)
    loaded = load_mqtt_config(path)

    assert loaded == config


def test_round_trip_username_without_password(tmp_path: Path) -> None:
    path = tmp_path / "mqtt.json"
    config = _config(username="alice", password=None)

    save_mqtt_config(path, config)
    loaded = load_mqtt_config(path)

    assert loaded == config


def test_save_omits_null_credential_fields_from_the_file(tmp_path: Path) -> None:
    """The desktop shape (no credentials) never writes username/password keys, not even null."""
    path = tmp_path / "mqtt.json"
    save_mqtt_config(path, _config())

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "username" not in raw
    assert "password" not in raw


def test_save_includes_credential_fields_when_present(tmp_path: Path) -> None:
    """The Docker shape (credentials present) writes both fields."""
    path = tmp_path / "mqtt.json"
    save_mqtt_config(path, _config(username="alice", password="secret"))

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["username"] == "alice"
    assert raw["password"] == "secret"


def test_save_omits_password_key_when_only_username_is_set(tmp_path: Path) -> None:
    path = tmp_path / "mqtt.json"
    save_mqtt_config(path, _config(username="alice", password=None))

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["username"] == "alice"
    assert "password" not in raw


def test_save_restricts_file_permissions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """save_mqtt_config chmods the file to 0600, since it may hold credentials."""
    chmod_calls: list[int] = []
    original_chmod = Path.chmod

    def _recording_chmod(self: Path, mode: int) -> None:
        chmod_calls.append(mode)
        original_chmod(self, mode)

    monkeypatch.setattr(Path, "chmod", _recording_chmod)

    save_mqtt_config(tmp_path / "mqtt.json", _config(username="alice", password="secret"))

    assert 0o600 in chmod_calls


def test_delete_removes_file(tmp_path: Path) -> None:
    path = tmp_path / "mqtt.json"
    save_mqtt_config(path, _config())
    assert path.exists()

    delete_mqtt_config(path)

    assert not path.exists()
    assert load_mqtt_config(path) is None


def test_delete_missing_file_is_a_no_op(tmp_path: Path) -> None:
    delete_mqtt_config(tmp_path / "mqtt.json")  # must not raise


# --- malformed/tolerant loading ---


def test_malformed_json_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "mqtt.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert load_mqtt_config(path) is None


def test_json_not_an_object_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "mqtt.json"
    path.write_text("[]", encoding="utf-8")
    assert load_mqtt_config(path) is None


@pytest.mark.parametrize(
    "data",
    [
        '{"port": 1883, "topic": "t", "tls": false}',  # missing host
        '{"host": "h", "topic": "t", "tls": false}',  # missing port
        '{"host": "h", "port": "1883", "topic": "t", "tls": false}',  # port not an int
        '{"host": "h", "port": 1883, "tls": false}',  # missing topic
        '{"host": "h", "port": 1883, "topic": "t"}',  # missing tls
        '{"host": "h", "port": 1883, "topic": "t", "tls": "false"}',  # tls not a bool
        '{"host": "", "port": 1883, "topic": "t", "tls": false}',  # empty host
    ],
)
def test_missing_or_invalid_required_fields_return_none(tmp_path: Path, data: str) -> None:
    path = tmp_path / "mqtt.json"
    path.write_text(data, encoding="utf-8")
    assert load_mqtt_config(path) is None


# --- keyring credential storage ---


def test_get_stored_credentials_when_none_stored_returns_none_none(
    fake_keyring: _FakeKeyring,
) -> None:
    assert get_stored_credentials() == (None, None)


def test_set_and_get_credentials_with_password(fake_keyring: _FakeKeyring) -> None:
    set_credentials("alice", "secret")
    assert get_stored_credentials() == ("alice", "secret")


def test_set_credentials_without_password_stores_username_only(
    fake_keyring: _FakeKeyring,
) -> None:
    set_credentials("alice", None)
    assert get_stored_credentials() == ("alice", None)


def test_set_credentials_with_empty_password_is_treated_as_none(
    fake_keyring: _FakeKeyring,
) -> None:
    set_credentials("alice", "")
    assert get_stored_credentials() == ("alice", None)


def test_replacing_password_with_none_clears_the_stored_password(
    fake_keyring: _FakeKeyring,
) -> None:
    set_credentials("alice", "secret")
    set_credentials("alice", None)
    assert get_stored_credentials() == ("alice", None)


def test_clear_credentials_removes_both(fake_keyring: _FakeKeyring) -> None:
    set_credentials("alice", "secret")
    clear_credentials()
    assert get_stored_credentials() == (None, None)


def test_clear_credentials_when_nothing_stored_does_not_raise(
    fake_keyring: _FakeKeyring,
) -> None:
    clear_credentials()  # must not raise
    assert get_stored_credentials() == (None, None)


def test_credentials_use_dedicated_keyring_service(fake_keyring: _FakeKeyring) -> None:
    """MQTT credentials are stored under their own service name, not MaxMind's."""
    set_credentials("alice", "secret")
    assert fake_keyring.get_password(KEYRING_SERVICE, "username") == "alice"
    assert fake_keyring.get_password("tapmap_geolite2", "username") is None
