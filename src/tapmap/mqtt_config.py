"""MQTT configuration and credential storage.

mqtt.json holds the connection settings (host, port, topic, TLS) for both
desktop and Docker. On desktop, username/password are never written to that
file - they live in the OS keyring, following the same approach as the
existing MaxMind credentials (see geodb/maxmind.py). Docker has no usable OS
keyring, so there username/password are stored in mqtt.json alongside the
rest of the configuration, protected by file permissions.

Absence of mqtt.json means MQTT is not configured. Nothing here creates it
automatically; it is written only through the interactive --configure-mqtt
command (mqtt_cli.py).
"""

from __future__ import annotations

import contextlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import keyring

MQTT_CONFIG_FILENAME = "mqtt.json"

KEYRING_SERVICE = "tapmap_mqtt"
USERNAME_KEY = "username"
PASSWORD_KEY = "password"


@dataclass(frozen=True)
class MqttConfig:
    """Resolved MQTT connection configuration.

    username/password are populated only for the Docker variant of this
    config; on desktop they are always None here and are stored in the OS
    keyring instead.
    """

    host: str
    port: int
    topic: str
    tls: bool
    username: str | None = None
    password: str | None = None


def mqtt_config_path(app_data_dir: Path) -> Path:
    """Return the path to mqtt.json for the given app data directory."""
    return app_data_dir / MQTT_CONFIG_FILENAME


def load_mqtt_config(path: Path) -> MqttConfig | None:
    """Load MqttConfig from a JSON file.

    Args:
        path: Path to the mqtt.json file.

    Returns:
        MqttConfig, or None if the file is missing, corrupt, or malformed.
    """
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return None

        host = data.get("host")
        port = data.get("port")
        topic = data.get("topic")
        tls = data.get("tls")

        if not isinstance(host, str) or not host:
            return None
        if not isinstance(port, int):
            return None
        if not isinstance(topic, str) or not topic:
            return None
        if not isinstance(tls, bool):
            return None

        username = data.get("username")
        password = data.get("password")

        return MqttConfig(
            host=host,
            port=port,
            topic=topic,
            tls=tls,
            username=username if isinstance(username, str) else None,
            password=password if isinstance(password, str) else None,
        )
    except Exception:
        return None


def save_mqtt_config(path: Path, config: MqttConfig) -> None:
    """Save MqttConfig to a JSON file atomically.

    username/password are omitted from the file entirely when None, rather
    than written as null, so a desktop config (which never sets them) never
    contains those keys at all.

    Args:
        path: Path to the mqtt.json file.
        config: MqttConfig to persist.

    Raises:
        OSError: If the file cannot be written or replaced.
    """
    data = asdict(config)
    if data["username"] is None:
        del data["username"]
    if data["password"] is None:
        del data["password"]

    tmp_path = path.with_suffix(".tmp")

    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()

    # Restrict permissions before the file becomes visible at its final path,
    # since it may contain credentials (the Docker configuration variant).
    tmp_path.chmod(0o600)

    # The temporary file has been closed. Retry the atomic replace in
    # case another process briefly locks the destination file.
    for attempt in range(6):
        try:
            tmp_path.replace(path)
            return

        except OSError:
            if attempt == 5:
                raise

            time.sleep(1)


def delete_mqtt_config(path: Path) -> None:
    """Delete mqtt.json if it exists. A no-op if it does not."""
    path.unlink(missing_ok=True)


def get_stored_credentials() -> tuple[str | None, str | None]:
    """Return the desktop MQTT username/password stored in the OS keyring."""
    username = keyring.get_password(KEYRING_SERVICE, USERNAME_KEY)
    password = keyring.get_password(KEYRING_SERVICE, PASSWORD_KEY)
    return username, password


def set_credentials(username: str, password: str | None) -> None:
    """Store the desktop MQTT username/password in the OS keyring.

    A missing/empty password clears any previously stored password rather
    than storing an empty string, since MQTT allows username-only auth.
    """
    keyring.set_password(KEYRING_SERVICE, USERNAME_KEY, username)

    if password:
        keyring.set_password(KEYRING_SERVICE, PASSWORD_KEY, password)
    else:
        _delete_password_if_present(PASSWORD_KEY)


def clear_credentials() -> None:
    """Remove any stored desktop MQTT username/password from the OS keyring."""
    _delete_password_if_present(USERNAME_KEY)
    _delete_password_if_present(PASSWORD_KEY)


def _delete_password_if_present(key: str) -> None:
    """Delete one keyring entry, tolerating it not being present."""
    with contextlib.suppress(keyring.errors.PasswordDeleteError):
        keyring.delete_password(KEYRING_SERVICE, key)
