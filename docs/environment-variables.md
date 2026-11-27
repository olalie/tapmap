# Environment Variables

TapMap supports a small set of environment variables that override the default runtime configuration.

TapMap works without environment variables and uses sensible defaults.

Environment variables allow specific settings to be overridden without modifying the source code or rebuilding the application.

Common uses include:

- Using a different port when the default port is already in use.
- Storing application data in a custom location.
- Using a fixed location instead of automatic public-IP based location detection.
- Configuring TapMap when running in Docker.

The examples below apply to a single start from a terminal. To keep settings for the application menu and automatic launch at login on Linux, see [Persistent configuration on Linux](#persistent-configuration-on-linux).

## TAPMAP_PORT

Override the HTTP port used by the local Dash server.

Default:

```text
8050
```

Examples:

Linux / macOS:

```bash
TAPMAP_PORT=8060 tapmap
```

PowerShell:

```powershell
$env:TAPMAP_PORT="8060"
tapmap.exe
```

Command Prompt:

```cmd
set TAPMAP_PORT=8060
tapmap.exe
```

This setting is useful when the default port is already in use.

## TAPMAP_HOST

Override the server bind address.

Example:

```bash
TAPMAP_HOST=0.0.0.0 tapmap
```

If not specified, TapMap normally binds to:

```text
127.0.0.1
```

When running in Docker, TapMap uses:

```text
0.0.0.0
```

unless overridden by `TAPMAP_HOST`.

The default Docker setting allows TapMap to be accessed from other machines on the network.

The About view shows the server host and port that TapMap uses.

### Security

`TAPMAP_HOST=0.0.0.0` makes TapMap listen on all network interfaces. Other devices that can reach the computer can then open TapMap.

The web interface has no authentication. Anyone who can reach the port can see your network connections, applications and processes, and can use the same functions as you.

Use `0.0.0.0` only on trusted networks. Use firewall rules to limit access to trusted devices.

## TAPMAP_IN_DOCKER

Tell TapMap that it is running in Docker.

Docker deployments use:

```text
TAPMAP_IN_DOCKER=1
```

This changes Docker-specific runtime behavior, including the default server bind address and disabling desktop-only features such as the system tray and autostart.

The Docker Compose configuration sets this variable automatically. When using `docker run`, set it explicitly as shown in the Docker examples.

## TAPMAP_DATA_DIR

Override the application data directory.

By default, TapMap uses the operating system's standard per-user application data location.

The data directory contains:

- GeoIP databases
- README.txt
- Application-generated data

This setting is useful when you want to store TapMap data in a custom location.

## TAPMAP_LON and TAPMAP_LAT

Override automatic public-IP based location detection.

Both variables must be provided together.

Example:

```bash
TAPMAP_LON=10.7522 TAPMAP_LAT=59.9139 tapmap
```

If both values are present and valid, TapMap uses the specified coordinates for the local map marker.

If either value is missing or invalid, TapMap falls back to the configured location behavior.

This setting is useful when automatic location detection is inaccurate or when you prefer not to use public-IP based location detection.

## TAPMAP_LAUNCH_BROWSER

Control whether TapMap automatically opens the default web browser at startup.

Default:

```text
true
```

Values:

```text
true
false
```

Example:

```bash
TAPMAP_LAUNCH_BROWSER=false tapmap
```

The `--no-browser` command-line flag overrides this setting.

TapMap's **Run TapMap automatically** feature already starts TapMap without opening the browser, so this setting is not required for desktop autostart.

## TAPMAP_CACHE_RETENTION_MIN

Control how long inactive services remain visible on the map.

Default:

```text
0
```

Values:

```text
0     Keep cached services until Clear cache is used.
>0    Remove cached services not seen for the specified number of minutes.
```

Example:

```bash
TAPMAP_CACHE_RETENTION_MIN=15 tapmap
```

This setting affects only the map cache.

It does not affect the current network snapshot, Open Ports, LAN/LOCAL Services, Unmapped Services, or the 30-day Insights history.

## TAPMAP_NOTIFICATION_LEARNING_DAYS

Control how many active Insights days TapMap waits before sending notifications.

Default:

```text
7
```

Values:

```text
0–30
```

A value of `0` enables notifications immediately.

Example:

```bash
TAPMAP_NOTIFICATION_LEARNING_DAYS=0 tapmap
```

The learning period affects notifications only. Significant Connections are recorded during the learning period.

## Persistent configuration on Linux

This section applies to the Linux DEB package. It has been verified on Ubuntu 24.04 with GNOME (X11). Other Linux distributions and desktop environments have not been tested.

Manual launch from the application menu and automatic launch at login use separate `.desktop` files. Environment variables added to one file apply only to launches from that file.

| Launch method | File | Created by |
|---|---|---|
| Application menu | `/usr/share/applications/no.tip.tapmap.desktop` | The DEB package |
| Automatic launch at login | `~/.config/autostart/no.tip.tapmap.desktop` | TapMap, the first time it starts |

Shared settings are recommended. They use one file, need no administrator rights and are kept when TapMap is upgraded.

### Shared settings

Create `~/.config/environment.d/tapmap.conf` with one `KEY=VALUE` per line. Create the directory if it does not exist. Shell syntax such as `export` is not supported.

```text
TAPMAP_PORT=8060
TAPMAP_CACHE_RETENTION_MIN=60
```

Restart the computer after creating, changing or deleting the file. Logging out and in again is not always enough.

Limitations:

- Other applications in your user session, including terminals, may also inherit these environment variables.
- Variables in the `Exec` line of a `.desktop` file take precedence over this file.
- The default autostart entry includes `--no-browser`, which overrides `TAPMAP_LAUNCH_BROWSER`.

### Separate settings

Use separate settings if you need different settings for manual and automatic launch, or if shared settings do not work.

Add `env` and your variables to the start of the `Exec` line in the file you want to configure. Keep the executable path and arguments.

For automatic launch, edit `~/.config/autostart/no.tip.tapmap.desktop`:

```ini
Exec=env TAPMAP_PORT=8060 /usr/lib/tapmap/tapmap --no-browser
```

The change takes effect at the next login. Turning **Run TapMap automatically** on or off changes only the `Hidden` line, so your `Exec` line is kept.

For manual launch, do not edit the package entry. It requires administrator rights and is replaced when TapMap is upgraded. Edit a copy in your home directory instead:

```bash
mkdir -p ~/.local/share/applications
cp /usr/share/applications/no.tip.tapmap.desktop ~/.local/share/applications/
```

```ini
Exec=env TAPMAP_PORT=8060 tapmap
```

The copy replaces the package entry in the application menu. Log out and in again after creating, changing or deleting it. The copy survives upgrades but may need to be revised if TapMap changes the original package entry.

Limitations:

- To use the same settings for both launch methods, maintain them in both files.
- To restore the default autostart entry, delete it and turn on **Run TapMap automatically**.
- If TapMap cannot read the autostart file, for example if the `[Desktop Entry]` line is missing, the **Run TapMap automatically** menu item is disabled.
