# Privacy Policy

TapMap is designed to protect your privacy.

- TapMap processes network connection data locally on your computer.
- TapMap does not transmit connection data unless explicitly configured by the user. TapMap does not send analytics or telemetry.
- Geolocation is performed using local GeoIP databases stored on your computer.
- By default, TapMap queries a public IP lookup service to obtain your public IP address and estimate your location. This is used only to display the approximate origin of connections on the map. This request can be disabled by specifying your location manually.
- GeoIP databases are downloaded or updated only when explicitly requested by the user.
- TapMap stores a local `insights.json` file containing a rolling 30-day aggregate history of countries, autonomous systems (ASNs), ports, and application names. It does not contain IP addresses, process IDs, or executable paths.
- TapMap stores a local `significant_connections.json` file containing the most recent 500 individual connection events judged significant. These events include connection, process, application, verification, geographic, and network provider information, including remote IP addresses and executable paths.
- These files are stored only on your computer and are never transmitted or shared by TapMap.
- If MQTT notifications are configured, TapMap publishes new notification-eligible Significant Connection data to the MQTT broker configured by the user. The executable path is not included.

TapMap does not collect or sell user data.
