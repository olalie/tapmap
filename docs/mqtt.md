# MQTT

TapMap can publish new Significant Connections to an MQTT broker.

MQTT notifications are optional and are enabled when an MQTT connection is configured.

## Configure MQTT

Run the configuration wizard:

```text
tapmap --configure-mqtt
```

The wizard configures:

- Broker IP address
- Port
- Topic
- TLS
- Optional username and password

The broker address must be an IPv4 or IPv6 address. Hostnames, including `localhost`, are not supported so TapMap does not perform DNS lookups when connecting to the broker. The same restriction applies to manually edited `mqtt.json` files.

The default port is `1883` without TLS and `8883` with TLS.

The default topic is:

```text
tapmap/significant_connections
```

Using authentication without TLS sends the MQTT credentials without encryption. TapMap warns before saving this configuration.

## Notification behavior

Significant Connections are recorded independently of MQTT notifications.

By default, notifications start after 7 active Insights days. Set `TAPMAP_NOTIFICATION_LEARNING_DAYS` to a value from `0` to `30` to change the learning period. A value of `0` enables notifications immediately.

Each new notification-eligible Significant Connection is published as one MQTT message.

Messages use QoS 0 and are not retained. Delivery is best effort; TapMap does not maintain a retry queue.

TapMap reconnects automatically if the MQTT connection is interrupted.

## Configuration and credentials

MQTT settings are stored in `mqtt.json` in the TapMap application data directory.

On desktop installations, MQTT credentials are stored separately in the operating system keyring and are not written to `mqtt.json`.

Docker stores both the MQTT settings and credentials in `/data/mqtt.json`. See [Docker](docker.md) for Docker-specific configuration.

## Message format

Each MQTT message contains the Significant Connection data as JSON.

The executable path is not included because it may contain the operating system username.

Example:

```json
{
  "timestamp": "2026-09-09T22:34:39.248916",
  "reasons": ["new_country", "new_provider"],
  "pid": 889,
  "proto": "tcp",
  "ip": "154.118.230.167",
  "port": 443,
  "service": "https",
  "lat": -6.1749,
  "lon": 35.7356,
  "process_name": "firefox",
  "city": "Dodoma",
  "country": "Tanzania",
  "country_code": "TZ",
  "asn": 327795,
  "asn_org": "e-Government Authority",
  "app_name": "Firefox",
  "app_creator": "Mozilla Corporation",
  "app_verification_status": "verified",
  "app_signature_state": "DeveloperSigned",
  "app_signature_state_details": "Notarized"
}
```

Fields without a value are published as JSON `null`.
