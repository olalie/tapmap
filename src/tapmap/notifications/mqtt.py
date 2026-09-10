"""Publish Significant Connection notifications over MQTT."""

from __future__ import annotations

import json
import logging
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
        """Disconnect from the broker and stop the MQTT network thread."""
        # disconnect() only queues the packet; the network loop sends it,
        # so it must run before loop_stop() stops that loop.
        self._client.disconnect()
        self._client.loop_stop()

    # The callbacks below must not modify ConnectionAnalyzer, Significant
    # Connections, Insights, UI, or other TapMap application state.

    def _on_connect(
        self, client: Any, userdata: Any, connect_flags: Any, reason_code: Any, properties: Any
    ) -> None:
        """Handle an MQTT connection result."""
        if reason_code.is_failure:
            self._report_failure(f"MQTT connection failed: {reason_code}")
        else:
            logger.info("MQTT connected.")
            self._connected = True
            self._last_reported_failure = None

    def _on_disconnect(
        self, client: Any, userdata: Any, disconnect_flags: Any, reason_code: Any, properties: Any
    ) -> None:
        """Handle an MQTT disconnection."""
        if not reason_code.is_failure:
            logger.info("MQTT disconnected: %s", reason_code)
            self._connected = False
            return

        if not self._connected:
            # A failure disconnect while already disconnected can be the echo
            # of the same failed connection attempt - do not log it again.
            return

        self._connected = False
        self._report_failure(f"MQTT disconnected: {reason_code}")

    def _on_connect_fail(self, client: Any, userdata: Any) -> None:
        """Handle an MQTT connection failure before CONNACK."""
        # paho provides no reason here - do not invent or imply one.
        self._report_failure("MQTT connection attempt failed.")

    def _report_failure(self, message: str) -> None:
        """Log a changed MQTT failure without repeating identical failures."""
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
    """Build an MQTT payload without the executable path."""
    # exe can embed the OS username, so it is excluded from the payload.
    return {key: value for key, value in event.items() if key != "exe"}
