# Environment Variables

TapMap supports a small set of environment variables that override the default runtime configuration.

TapMap works without environment variables and uses sensible defaults.

Environment variables allow specific settings to be overridden without modifying the source code or rebuilding the application.

Common uses include:

- Using a different port when the default port is already in use.
- Storing application data in a custom location.
- Using a fixed location instead of automatic public-IP based location detection.
- Configuring TapMap when running in Docker.

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
