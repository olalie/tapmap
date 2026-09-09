"""MQTT notification channel.

Publishes one MQTT message per eligible, newly accepted Significant
Connection. The paho-mqtt client and its background network thread live
entirely inside this module. The MQTT callbacks (_on_connect/_on_disconnect/
_on_connect_fail) handle connection lifecycle and logging only - they never
touch ConnectionAnalyzer, Significant Connections, Insights, UI state, or any
other TapMap application state. They track connection/failure state on the
MqttChannel instance itself, so a broker that stays unavailable or keeps
rejecting the same way does not re-log identical failures on every automatic
retry.
"""

from __future__ import annotations

import json
import logging
import socket
import ssl
from typing import TYPE_CHECKING, Any

import keyring.errors

from ..mqtt_config import get_stored_credentials, load_mqtt_config, mqtt_config_path

if TYPE_CHECKING:
    import paho.mqtt.client as mqtt

    from ..runtime import RuntimeContext

logger = logging.getLogger(__name__)


class MqttChannel:
    """Publish Significant Connection events to a configured MQTT broker."""

    def __init__(self, client: mqtt.Client, topic: str) -> None:
        self._client = client
        self._topic = topic
        self._connected = False
        self._last_reported_failure: str | None = None

    def send(self, event: dict[str, Any]) -> None:
        """Publish one Significant Connection event."""
        payload = _build_payload(event)
        info = self._client.publish(self._topic, json.dumps(payload), qos=0, retain=False)
        if info.rc:
            logger.debug("MQTT publish did not succeed immediately: %s", info.rc)

    def close(self) -> None:
        """Disconnect, then stop the network thread.

        disconnect() only queues the DISCONNECT packet; the still-running
        network thread is what flushes it and then exits on its own.
        Calling loop_stop() first would join that thread before the packet
        could ever be sent.
        """
        self._client.disconnect()
        self._client.loop_stop()

    def _on_connect(
        self, client: Any, userdata: Any, connect_flags: Any, reason_code: Any, properties: Any
    ) -> None:
        """Log the connection result. MQTT lifecycle/logging only."""
        if reason_code.is_failure:
            self._report_failure(f"MQTT connection failed: {reason_code}")
        else:
            logger.info("MQTT connected.")
            self._connected = True
            self._last_reported_failure = None

    def _on_disconnect(
        self, client: Any, userdata: Any, disconnect_flags: Any, reason_code: Any, properties: Any
    ) -> None:
        """Log the disconnection. MQTT lifecycle/logging only.

        A failure-flagged disconnect while _connected is already False is the
        same-attempt echo paho raises right after a rejected CONNACK (always
        reported as a generic "Unspecified error", carrying no information
        _on_connect didn't already report) - it is not logged again.
        """
        if not reason_code.is_failure:
            logger.info("MQTT disconnected: %s", reason_code)
            self._connected = False
            return

        if not self._connected:
            return

        self._connected = False
        self._report_failure(f"MQTT disconnected: {reason_code}")

    def _on_connect_fail(self, client: Any, userdata: Any) -> None:
        """Log a failed pre-CONNACK connection attempt. MQTT lifecycle/logging only.

        paho calls this for any connection attempt that fails before a CONNACK
        is exchanged (DNS, TCP, or TLS failures alike) and does not pass a
        reason - on_connect/on_disconnect never fire for these attempts, so
        without this callback they are silent.
        """
        self._report_failure("MQTT connection attempt failed.")

    def _report_failure(self, message: str) -> None:
        """Log message as WARNING unless it repeats the last reported failure.

        Keeps a broker that stays down or keeps rejecting the same way from
        producing one warning per automatic retry; a genuinely different
        failure, or a fresh failure after a successful connection, still logs.
        """
        if message != self._last_reported_failure:
            logger.warning(message)
            self._last_reported_failure = message


def create_mqtt_channel(runtime: RuntimeContext) -> MqttChannel | None:
    """Build the MQTT channel from mqtt.json, or return None if unconfigured/unavailable."""
    config = load_mqtt_config(mqtt_config_path(runtime.app_data_dir))
    if config is None:
        return None

    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        logger.warning("paho-mqtt is not installed; MQTT notifications are unavailable.")
        return None

    if runtime.is_docker:
        username, password = config.username, config.password
    else:
        try:
            username, password = get_stored_credentials()
        except keyring.errors.KeyringError:
            logger.warning(
                "Unable to read MQTT credentials from the OS keyring; "
                "MQTT notifications are unavailable.",
                exc_info=True,
            )
            return None

    if username and not config.tls:
        logger.warning(
            "MQTT authentication is configured without TLS; credentials will be "
            "sent in plaintext over the network."
        )

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)

    if username:
        client.username_pw_set(username, password)

    if config.tls:
        try:
            client.tls_set()
        except (ssl.SSLError, ValueError):
            logger.warning(
                "Unable to configure MQTT TLS; MQTT notifications are unavailable.",
                exc_info=True,
            )
            return None

    channel = MqttChannel(client, config.topic)
    client.on_connect = channel._on_connect
    client.on_disconnect = channel._on_disconnect
    client.on_connect_fail = channel._on_connect_fail

    client.connect_async(config.host, config.port)
    client.loop_start()

    return channel


def _build_payload(event: dict[str, Any]) -> dict[str, Any]:
    """Return the MQTT payload for one Significant Connection event.

    The complete event, unchanged, except exe (a local filesystem path that
    can embed the OS username) is excluded and hostname is added.
    """
    payload = {key: value for key, value in event.items() if key != "exe"}
    payload["hostname"] = socket.gethostname()
    return payload
