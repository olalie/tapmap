"""Tests for the interactive `tapmap --configure-mqtt` flow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import keyring
import keyring.errors
import pytest

from tapmap.app import APP_META
from tapmap.mqtt_cli import _derive_default_port, run_configure_mqtt
from tapmap.mqtt_config import (
    MqttConfig,
    get_stored_credentials,
    load_mqtt_config,
    mqtt_config_path,
    save_mqtt_config,
)
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


def _scripted(answers: list[str], *, asked: list[str] | None = None) -> Any:
    """Return a callable that pops canned answers in order.

    If asked is given, every question text passed to the callable is
    recorded there, in order.
    """
    remaining = list(answers)

    def _prompt(question: str) -> str:
        if asked is not None:
            asked.append(question)
        if not remaining:
            raise AssertionError(f"No more scripted answers; unexpected prompt: {question!r}")
        return remaining.pop(0)

    return _prompt


def _capturing() -> tuple[Any, list[str]]:
    """Return an output callable and the list it appends printed lines to."""
    lines: list[str] = []
    return lines.append, lines


def _existing_config(**overrides: object) -> MqttConfig:
    values: dict[str, object] = {
        "host": "old.example.com",
        "port": 1883,
        "topic": "old/topic",
        "tls": False,
    }
    values.update(overrides)
    return MqttConfig(**values)  # type: ignore[arg-type]


# --- fresh setup ---


def test_fresh_setup_without_auth(tmp_path: Path, fake_keyring: _FakeKeyring) -> None:
    runtime = _runtime_ctx(tmp_path)
    output, lines = _capturing()
    secret_calls: list[str] = []

    result = run_configure_mqtt(
        runtime,
        prompt=_scripted(["broker.local", "n", "", "", "n"]),
        prompt_secret=lambda q: secret_calls.append(q) or "unused",
        output=output,
    )

    assert result == 0
    config = load_mqtt_config(mqtt_config_path(tmp_path))
    assert config == MqttConfig(
        host="broker.local",
        port=1883,
        topic="tapmap/significant_connections",
        tls=False,
        username=None,
        password=None,
    )
    assert secret_calls == []  # never prompted for a password when auth is off
    assert any("saved" in line.lower() for line in lines)


def test_fresh_setup_with_tls_derives_default_port(
    tmp_path: Path, fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path)

    run_configure_mqtt(
        runtime,
        prompt=_scripted(["broker.local", "y", "", "", "n"]),
        output=_capturing()[0],
    )

    config = load_mqtt_config(mqtt_config_path(tmp_path))
    assert config is not None
    assert config.tls is True
    assert config.port == 8883


def test_fresh_setup_with_auth_desktop_stores_in_keyring(
    tmp_path: Path, fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path, is_docker=False)

    run_configure_mqtt(
        runtime,
        prompt=_scripted(["broker.local", "n", "", "", "y", "alice", "y"]),
        prompt_secret=lambda q: "secret1",
        output=_capturing()[0],
    )

    config = load_mqtt_config(mqtt_config_path(tmp_path))
    assert config is not None
    assert config.username is None
    assert config.password is None
    assert get_stored_credentials() == ("alice", "secret1")


def test_password_prompt_is_preceded_by_hidden_input_notice(
    tmp_path: Path, fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path, is_docker=False)
    output, lines = _capturing()

    run_configure_mqtt(
        runtime,
        prompt=_scripted(["broker.local", "n", "", "", "y", "alice", "y"]),
        prompt_secret=lambda q: "secret1",
        output=output,
    )

    assert "Input is hidden - nothing will appear as you type." in lines


def test_fresh_setup_with_auth_docker_stores_in_file(
    tmp_path: Path, fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path, is_docker=True)

    run_configure_mqtt(
        runtime,
        prompt=_scripted(["broker.local", "n", "", "", "y", "alice", "y"]),
        prompt_secret=lambda q: "secret1",
        output=_capturing()[0],
    )

    config = load_mqtt_config(mqtt_config_path(tmp_path))
    assert config is not None
    assert config.username == "alice"
    assert config.password == "secret1"
    assert get_stored_credentials() == (None, None)  # keyring untouched in Docker


def test_username_without_password_is_allowed(tmp_path: Path, fake_keyring: _FakeKeyring) -> None:
    runtime = _runtime_ctx(tmp_path, is_docker=True)

    run_configure_mqtt(
        runtime,
        prompt=_scripted(["broker.local", "n", "", "", "y", "alice", "y"]),
        prompt_secret=lambda q: "",  # left empty
        output=_capturing()[0],
    )

    config = load_mqtt_config(mqtt_config_path(tmp_path))
    assert config is not None
    assert config.username == "alice"
    assert config.password is None


def test_host_is_required_and_reprompts_on_blank(
    tmp_path: Path, fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path)

    run_configure_mqtt(
        runtime,
        prompt=_scripted(["", "", "broker.local", "n", "", "", "n"]),
        output=_capturing()[0],
    )

    config = load_mqtt_config(mqtt_config_path(tmp_path))
    assert config is not None
    assert config.host == "broker.local"


def test_invalid_port_reprompts(tmp_path: Path, fake_keyring: _FakeKeyring) -> None:
    runtime = _runtime_ctx(tmp_path)

    run_configure_mqtt(
        runtime,
        prompt=_scripted(["broker.local", "n", "abc", "70000", "9000", "", "n"]),
        output=_capturing()[0],
    )

    config = load_mqtt_config(mqtt_config_path(tmp_path))
    assert config is not None
    assert config.port == 9000


# --- reconfigure / disable ---


def test_reconfigure_keeps_existing_credentials_on_desktop(
    tmp_path: Path, fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path, is_docker=False)
    save_mqtt_config(mqtt_config_path(tmp_path), _existing_config())
    fake_keyring.set_password("tapmap_mqtt", "username", "alice")
    fake_keyring.set_password("tapmap_mqtt", "password", "secret1")

    run_configure_mqtt(
        runtime,
        prompt=_scripted(["n", "new.example.com", "y", "", "", "y", "y"]),
        output=_capturing()[0],
    )

    config = load_mqtt_config(mqtt_config_path(tmp_path))
    assert config is not None
    assert config.host == "new.example.com"
    assert config.tls is True
    # existing port (1883) was the standard port for the old TLS=off setting,
    # and TLS just changed to on, so the standard port for TLS=on is proposed
    # and accepted here via the blank answer - see _derive_default_port.
    assert config.port == 8883
    assert config.username is None
    assert get_stored_credentials() == ("alice", "secret1")  # untouched


def test_reconfigure_replaces_credentials_on_docker(
    tmp_path: Path, fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path, is_docker=True)
    save_mqtt_config(mqtt_config_path(tmp_path), _existing_config(username="alice", password="old"))

    run_configure_mqtt(
        runtime,
        prompt=_scripted(["n", "new.example.com", "n", "", "", "y", "n", "bob", "y"]),
        prompt_secret=lambda q: "newpass",
        output=_capturing()[0],
    )

    config = load_mqtt_config(mqtt_config_path(tmp_path))
    assert config is not None
    assert config.username == "bob"
    assert config.password == "newpass"


def test_turning_auth_off_clears_desktop_keyring(
    tmp_path: Path, fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path, is_docker=False)
    save_mqtt_config(mqtt_config_path(tmp_path), _existing_config())
    fake_keyring.set_password("tapmap_mqtt", "username", "alice")
    fake_keyring.set_password("tapmap_mqtt", "password", "secret1")

    run_configure_mqtt(
        runtime,
        prompt=_scripted(["n", "new.example.com", "n", "", "", "n"]),
        output=_capturing()[0],
    )

    assert get_stored_credentials() == (None, None)


def test_disable_deletes_file_and_clears_desktop_credentials(
    tmp_path: Path, fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path, is_docker=False)
    path = mqtt_config_path(tmp_path)
    save_mqtt_config(path, _existing_config())
    fake_keyring.set_password("tapmap_mqtt", "username", "alice")
    fake_keyring.set_password("tapmap_mqtt", "password", "secret1")

    output, lines = _capturing()
    result = run_configure_mqtt(runtime, prompt=_scripted(["y"]), output=output)

    assert result == 0
    assert not path.exists()
    assert get_stored_credentials() == (None, None)
    assert any("disabled" in line.lower() for line in lines)


def test_disable_on_docker_does_not_touch_keyring(
    tmp_path: Path, fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path, is_docker=True)
    path = mqtt_config_path(tmp_path)
    save_mqtt_config(path, _existing_config(username="alice", password="secret1"))

    run_configure_mqtt(runtime, prompt=_scripted(["y"]), output=_capturing()[0])

    assert not path.exists()
    assert get_stored_credentials() == (None, None)  # never touched keyring at all


# --- failure handling ---


def test_save_failure_returns_nonzero_and_does_not_raise(
    tmp_path: Path, fake_keyring: _FakeKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime_ctx(tmp_path)

    def _raise_oserror(path: Path, config: MqttConfig) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("tapmap.mqtt_cli.save_mqtt_config", _raise_oserror)

    output, lines = _capturing()
    result = run_configure_mqtt(
        runtime,
        prompt=_scripted(["broker.local", "n", "", "", "n"]),
        output=output,
    )

    assert result == 1
    assert any("unable to save" in line.lower() for line in lines)


# --- plaintext-credentials-without-TLS warning ---


def test_plaintext_auth_warning_uses_exact_wording(
    tmp_path: Path, fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path, is_docker=False)
    asked: list[str] = []

    run_configure_mqtt(
        runtime,
        prompt=_scripted(["broker.local", "n", "", "", "y", "alice", "y"], asked=asked),
        prompt_secret=lambda q: "secret1",
        output=_capturing()[0],
    )

    assert any(
        q.startswith(
            "Username/password without TLS sends credentials in plaintext "
            "over the network. Continue? [y/N] "
        )
        for q in asked
    )


def test_declining_plaintext_auth_warning_saves_nothing(
    tmp_path: Path, fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path, is_docker=False)
    output, lines = _capturing()

    result = run_configure_mqtt(
        runtime,
        prompt=_scripted(["broker.local", "n", "", "", "y", "alice", "n"]),
        prompt_secret=lambda q: "secret1",
        output=output,
    )

    assert result == 0
    assert not mqtt_config_path(tmp_path).exists()
    assert get_stored_credentials() == (None, None)
    assert any("not saved" in line.lower() for line in lines)


def test_declining_plaintext_auth_warning_does_not_change_docker_config(
    tmp_path: Path, fake_keyring: _FakeKeyring
) -> None:
    runtime = _runtime_ctx(tmp_path, is_docker=True)
    path = mqtt_config_path(tmp_path)
    save_mqtt_config(path, _existing_config(username="alice", password="old"))

    run_configure_mqtt(
        runtime,
        prompt=_scripted(["n", "new.example.com", "n", "", "", "y", "n", "bob", "n"]),
        prompt_secret=lambda q: "newpass",
        output=_capturing()[0],
    )

    config = load_mqtt_config(path)
    assert config == _existing_config(username="alice", password="old")


def test_no_warning_when_auth_is_off(tmp_path: Path, fake_keyring: _FakeKeyring) -> None:
    """TLS off with no auth requested never prompts the plaintext warning."""
    runtime = _runtime_ctx(tmp_path, is_docker=False)
    asked: list[str] = []

    result = run_configure_mqtt(
        runtime,
        prompt=_scripted(["broker.local", "n", "", "", "n"], asked=asked),
        output=_capturing()[0],
    )

    assert result == 0
    assert not any("plaintext" in q.lower() for q in asked)


# --- credential changes deferred until after a successful save ---


def test_failed_save_does_not_set_desktop_keyring_credentials(
    tmp_path: Path, fake_keyring: _FakeKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime_ctx(tmp_path, is_docker=False)

    def _raise_oserror(path: Path, config: MqttConfig) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("tapmap.mqtt_cli.save_mqtt_config", _raise_oserror)

    result = run_configure_mqtt(
        runtime,
        # tls=y so this exercises point 4 in isolation, without the
        # plaintext warning from point 3 also being in play.
        prompt=_scripted(["broker.local", "y", "", "", "y", "alice"]),
        prompt_secret=lambda q: "secret1",
        output=_capturing()[0],
    )

    assert result == 1
    assert get_stored_credentials() == (None, None)


def test_failed_save_does_not_clear_desktop_keyring_credentials(
    tmp_path: Path, fake_keyring: _FakeKeyring, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _runtime_ctx(tmp_path, is_docker=False)
    save_mqtt_config(mqtt_config_path(tmp_path), _existing_config())
    fake_keyring.set_password("tapmap_mqtt", "username", "alice")
    fake_keyring.set_password("tapmap_mqtt", "password", "secret1")

    def _raise_oserror(path: Path, config: MqttConfig) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("tapmap.mqtt_cli.save_mqtt_config", _raise_oserror)

    result = run_configure_mqtt(
        runtime,
        prompt=_scripted(["n", "new.example.com", "n", "", "", "n"]),
        output=_capturing()[0],
    )

    assert result == 1
    assert get_stored_credentials() == ("alice", "secret1")


# --- default port derivation when TLS changes on reconfigure ---


def test_derive_default_port_fresh_setup_plain() -> None:
    assert _derive_default_port(None, False) == 1883


def test_derive_default_port_fresh_setup_tls() -> None:
    assert _derive_default_port(None, True) == 8883


def test_derive_default_port_standard_port_follows_tls_off_to_on() -> None:
    existing = _existing_config(tls=False, port=1883)
    assert _derive_default_port(existing, True) == 8883


def test_derive_default_port_standard_port_follows_tls_on_to_off() -> None:
    existing = _existing_config(tls=True, port=8883)
    assert _derive_default_port(existing, False) == 1883


def test_derive_default_port_unchanged_tls_keeps_existing_port() -> None:
    existing = _existing_config(tls=False, port=1883)
    assert _derive_default_port(existing, False) == 1883


def test_derive_default_port_custom_port_preserved_off_to_on() -> None:
    existing = _existing_config(tls=False, port=9000)
    assert _derive_default_port(existing, True) == 9000


def test_derive_default_port_custom_port_preserved_on_to_off() -> None:
    existing = _existing_config(tls=True, port=9000)
    assert _derive_default_port(existing, False) == 9000


def test_derive_default_port_nonstandard_pairing_is_treated_as_custom() -> None:
    """Port 1883 while TLS was already on doesn't match the old standard, so it's preserved."""
    existing = _existing_config(tls=True, port=1883)
    assert _derive_default_port(existing, False) == 1883


def test_reconfigure_end_to_end_proposes_tls_standard_port(
    tmp_path: Path, fake_keyring: _FakeKeyring
) -> None:
    """The derived default is actually wired into the reconfigure prompt flow."""
    runtime = _runtime_ctx(tmp_path, is_docker=False)
    save_mqtt_config(mqtt_config_path(tmp_path), _existing_config(tls=False, port=1883))

    run_configure_mqtt(
        runtime,
        # disable?no, host(""->keep old), tls=y, port(""->accept shown default), topic(""), auth off
        prompt=_scripted(["n", "", "y", "", "", "n"]),
        output=_capturing()[0],
    )

    config = load_mqtt_config(mqtt_config_path(tmp_path))
    assert config is not None
    assert config.port == 8883
