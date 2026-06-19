# Docker

TapMap supports running in Docker on Linux hosts.

Docker support is intended for users who want to monitor network activity on a Linux system without installing TapMap directly on the host.

Docker Desktop on Windows and macOS is not supported.

## Run from Docker Hub


The published Docker image supports:

- AMD64 (x86_64)
- ARM64

Create a local data directory:

```bash
mkdir -p ~/tapmap-data
```

Start TapMap:

```bash
docker run --rm \
  --network host \
  --pid host \
  -v ~/tapmap-data:/data \
  -e TAPMAP_IN_DOCKER=1 \
  olalie/tapmap:latest
```

The mounted host directory is used as the container data directory (`/data`).

If no supported GeoIP databases are found, GeoIP Database Management opens automatically and guides you through the installation process.

Open:

```text
http://127.0.0.1:8050
```

## Access from another machine

By default, TapMap listens on:

```text
0.0.0.0
```

when running in Docker.

If the host machine has IP address:

```text
192.168.1.50
```

TapMap can be accessed from another machine using:

```text
http://192.168.1.50:8050
```

## Environment variables

TapMap supports runtime configuration through environment variables.

A common example is changing the default port:

```bash
-e TAPMAP_PORT=8060
```

See [Environment Variables](environment-variables.md) for details.

## Process information

TapMap always shows network activity.

Process visibility in Docker depends on host security policies.

On Ubuntu with the default Docker AppArmor profile (`docker-default`), `SYS_PTRACE` alone was not sufficient.

In this setup, process names became available with:

```bash
--cap-add=SYS_PTRACE
--security-opt apparmor=unconfined
```

Behavior may vary across systems.

## Updating the Docker image

Docker does not automatically download newer versions of an existing image.

To update:

```bash
docker pull olalie/tapmap:latest
```

or start the container with:

```bash
docker run --pull always ...
```

## Building a Docker image from source

For advanced users, a Docker image can be built directly from the repository.

Build the image:

```bash
docker build -t tapmap .
```

Start using the provided Docker Compose configuration:

```bash
docker compose -f compose_linux.yaml up
```

## GeoIP databases

TapMap requires GeoIP databases to display locations on the map.

GeoIP databases are stored in the directory mounted to `/data`.

For example:

```bash
-v ~/tapmap-data:/data
```

stores the databases in:

```text
~/tapmap-data
```

on the host system.

For installation, updates, manual installation, and provider selection, see [GeoIP Database Management](geodb-management.md).

## Troubleshooting

### No map locations

Verify that supported GeoIP databases are installed and detected.

See [GeoIP Database Management](geodb-management.md).

### Cannot access TapMap from another machine

Verify:

- The host machine is reachable on the network.
- Port 8050 is not blocked by a firewall.
- The correct host IP address is being used.
