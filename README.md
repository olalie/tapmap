<p align="center">
  <img src="docs/images/tapmap-logo.svg" width="100">
</p>

# TapMap

[![Latest version](https://img.shields.io/github/v/release/olalie/tapmap)](https://github.com/olalie/tapmap/releases) [![platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20Linux%20%7C%20macOS-blue)](https://github.com/olalie/tapmap/releases) [![Docker Pulls](https://img.shields.io/docker/pulls/olalie/tapmap)](https://hub.docker.com/r/olalie/tapmap) [![License](https://img.shields.io/github/license/olalie/tapmap?cacheSeconds=0)](https://github.com/olalie/tapmap/blob/main/LICENSE)

![TapMap demo](docs/images/demo.gif)

Featured in: [How-To Geek](https://www.howtogeek.com/this-self-hosted-global-map-revealed-how-my-network-connects-to-the-outside-world/) • [MakeUseOf](https://www.makeuseof.com/i-put-my-computers-internet-traffic-on-map-didnt-expect-what-found/) • [kode24](https://www.kode24.no/artikkel/da-pc-en-min-begynte-a-tegne-linjer-til-kina/263807)

**Watch your computer connect across the internet in real time. Discover the world behind your apps.**

Runs locally. No telemetry. Docker supported on Linux.

TapMap inspects local socket data, enriches IP addresses with geolocation, and visualizes the locations on an interactive map.

It also builds a local activity history to provide insights and identify patterns in network activity over time.

It is an awareness tool, not a firewall or a full security suite.
It makes network activity visible and easy to explore.

---

## Quick start

#### Download and run (Windows, Linux, macOS)

Download the latest version from the [Releases page](https://github.com/olalie/tapmap/releases).

Extract and start TapMap:

**Windows**

    tapmap.exe

**Linux and macOS**

    ./tapmap

**Note**

Windows and macOS may show a security warning the first time you run TapMap.

See:
- [Windows SmartScreen](#windows-smartscreen)
- [macOS security warning](#macos-security-warning)

#### Docker (Linux host only)

    docker run --rm \
    --network host \
    --pid host \
    -v ~/tapmap-data:/data \
    -e TAPMAP_IN_DOCKER=1 \
    olalie/tapmap:latest

For Docker configuration, updates, process visibility, and Docker Compose usage, see [Docker](https://olalie.github.io/tapmap/docker/).

---

## Why TapMap

Your computer connects to many systems without you noticing.

TapMap makes this visible so you can:

- See where connections go  
- Notice when something new appears  
- Understand what is normal over time  
- Explore connections with hover and click

---

## What TapMap shows

- Services your computer connects to  
- Their approximate locations on a world map  
- Nearby locations highlighted when multiple connections overlap  
- Insights panel showing new and frequent activity over time
- Daily Activity Report with application patterns, provider analysis, and activity timelines  
- Unmapped public services with missing geolocation  
- Established LAN and LOCAL services  
- Local open ports (TCP LISTEN and UDP bound)

All data is collected locally on your machine.

---

## How to use

- Hover map markers for a summary
- Click map markers for detailed information
- Open the menu in the upper-left corner to access Insights, network views, and application information
- Open the Daily Activity Report with D
- Click countries in Insights to zoom to the location

---

## Insights and Daily Activity Report

TapMap builds a rolling 30-day history of network activity and helps you understand what is normal, new, recurring, or unusual.

The Insights panel highlights:

- New apps, providers (ASN), countries, and ports
- Frequent activity (Top 5+, including ties)
- Click countries to zoom and inspect on the map

The Daily Activity Report provides a broader summary of recent activity:

- Application recurrence patterns (seen once, occasional, recurring, and stable)
- Provider concentration analysis
- Country activity visualization
- Generated activity logs with detailed timelines

The map shows connections observed since TapMap started or the cache was last cleared, while Insights and the Daily Activity Report use historical activity collected during the last 30 days.

To build a complete activity history, keep TapMap running while your system is in use. Running it at startup is recommended.

---

## How it works

TapMap follows a simple local pipeline:

    socket scan → IP extraction → GeoIP lookup → map rendering

It uses:

- `psutil` (Windows and Linux) or `lsof` (macOS) to read active network connections
- GeoIP databases for IP geolocation
- Dash and Plotly to render an interactive world map

---

## How it runs

TapMap runs locally as a web server and opens your browser:

http://127.0.0.1:8050/

If it does not open automatically, enter the address manually.

TapMap works with the default configuration.

Runtime configuration through environment variables is documented in [Environment Variables](https://olalie.github.io/tapmap/environment-variables/).

Users running TapMap from source can also adjust settings in `config.py`.

---

## GeoIP databases

TapMap uses GeoIP databases to display locations on the map.

If no supported databases are found, GeoIP Database Management opens automatically and guides you through database setup.

Installation, updates, provider selection, and manual installation are documented in [GeoIP Database Management](https://olalie.github.io/tapmap/geodb-management/).

---

## Documentation

Additional documentation:

- [Docker](https://olalie.github.io/tapmap/docker/)
- [GeoIP Database Management](https://olalie.github.io/tapmap/geodb-management/)
- [Environment Variables](https://olalie.github.io/tapmap/environment-variables/)
- [Backend Testing](https://olalie.github.io/tapmap/backend-testing/)

---

## Interface

![TapMap features](docs/images/features.gif)

#### Main view
Interactive world map with live connections, Insights, and quick access to major features.

![Main view](docs/images/menu_and_insights.png)

#### Daily Activity Report
Historical analysis of applications, providers, countries, and activity patterns observed during the last 30 days.

![Daily Activity Report](docs/images/daily_activity_report.png)

#### GeoIP Database Management
Install, update, verify, and manage GeoIP databases used for geolocation.

![GeoIP Database Management](docs/images/geoip_db_mgt.png)

#### Open ports
View local TCP listening ports and UDP bound ports, including processes and services.

![Open ports](docs/images/open-ports.png)

#### Unmapped services
Inspect connections that could not be geolocated and therefore do not appear on the map.

![Unmapped services](docs/images/unmapped-services.png)

---

## Keyboard controls

| Key | Action |
|-----|--------|
| D   | Daily Activity Report |
| I   | Toggle Insights panel |
| U   | Unmapped public services |
| L   | Established LAN/LOCAL services |
| O   | Open ports |
| G   | GeoIP Database Management |
| T   | Show cache in terminal |
| C   | Clear cache |
| H   | Help |
| A   | About |
| ESC | Close window |

---

## Privacy

- TapMap runs locally.
- No connection data is sent anywhere.
- Geolocation uses local GeoIP databases.
- If automatic local geolocation is enabled, TapMap contacts a public IP lookup service to determine your public IP address.
- External public-IP lookup can be avoided by using fixed local coordinates.
- GeoIP databases can be installed and updated from within TapMap or managed manually.

---

## Platforms and builds

Download the latest version from the [Releases page](https://github.com/olalie/tapmap/releases).

Available builds:

- Windows
- Linux
- macOS (Apple Silicon)
- macOS (Intel)

Tested on:

- Windows 11
- Ubuntu
- macOS (Apple Silicon)

Community testing has confirmed support on additional platforms and architectures.

Command-line options:

    tapmap --help

    tapmap --version
    tapmap -v

---

## Windows SmartScreen

Windows may show a SmartScreen warning the first time you run TapMap.  
This is normal for new applications that are not digitally signed.

To start the program:

1. Click **More info**.
2. Click **Run anyway**.

---

## macOS security warning

macOS may block the app the first time you run TapMap.
This is normal for unsigned applications.

To start the program:

1. Try to open the app.
2. Open **System Settings → Privacy & Security**.
3. Click **Open anyway** for TapMap.

You may be asked to confirm once more.

Alternatively, you can remove the warning using Terminal:

    xattr -d com.apple.quarantine tapmap

---

## Build from source

TapMap must be installed before running from source.

Requirements:

- Python 3.10+

Create virtual environment:

    python -m venv .venv

Activate:

    source .venv/bin/activate   (Linux/macOS)
    .venv\Scripts\activate      (Windows)

Install dependencies and package:

    pip install -r requirements.txt
    pip install -e .

Run (development mode):

    python -m tapmap

Run tests:

    pytest

---

#### Build executable (optional)

Build a standalone executable using PyInstaller:

    python tools/build.py

Output:

- Linux/macOS: dist/tapmap
- Windows: dist/tapmap.exe

Run:

    ./dist/tapmap      (Linux/macOS)
    dist\tapmap.exe    (Windows)

Note:

The executable must be built on the target operating system.

---

## Project

TapMap is developed by Ola Lie at TIP Teknologi i Praksis AS. Professional services include:

- TapMap support
- System development
- Data analysis

[https://tip.no](https://tip.no)

---

## License

MIT License

---

## Acknowledgements

Thanks to @faxotherapy for reporting macOS compatibility issues and testing Intel builds.  
Thanks to @nafarinha for confirming architecture support and validating macOS behavior.

Thanks to @totti4ever for reporting Docker multi-arch issues and confirming the fix on arm64.  
Thanks to @khadanja for suggesting a Docker-based workaround.

Thanks to @TechnVision for raising the configurable port use case.  
Thanks to @desrod for suggesting a solution for configurable port support.  
Thanks to @hugalafutro for suggesting optional SYS_PTRACE support for process visibility on Linux.

Thanks to @mad-tunes for suggesting optional browser launch control when running TapMap as a service, and configurable cache retention to reduce map clutter on busy systems.
