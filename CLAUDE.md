# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TapMap is a network connection visualization tool that monitors local TCP/UDP connections, enriches IPs with MaxMind GeoLite2 geolocation data, and displays them on an interactive Plotly map via a Dash web app. Runs entirely locally at `127.0.0.1:8050`.

## Commands

```bash
# Run the app
python tapmap.py

# Run tests
pytest
pytest tests/test_modal.py                    # single file
pytest tests/test_modal.py::test_decide_close  # single test

# Lint and format
ruff check .
ruff format .

# Build executable (PyInstaller)
python tools/build.py

# Docker (Linux only)
docker compose -f compose.linux.yaml up --build
```

## Architecture

**Data flow:** Socket data (lsof/psutil) → `Model.snapshot()` → GeoInfo enrichment → `StatusCache` → UI rendering (Dash/Plotly)

### Key layers

- **`tapmap.py`** — Entry point. Dash app setup and callback wiring. Delegates decisions to `state/` and rendering to `ui/`.

- **`model/`** — Data collection and enrichment.
  - `netinfo.py` — Protocol-based facade selecting platform backend.
  - `netinfo_lsof.py` — macOS backend (parses `lsof` output).
  - `netinfo_psutil.py` — Windows/Linux backend.
  - `geoinfo.py` — MaxMind GeoIP enrichment with LRU cache.
  - `model.py` — `Model.snapshot()` orchestrates collection + enrichment, returns typed `SnapshotPayload`.

- **`state/`** — Pure decision logic, **no Dash imports**. This makes all state transitions directly unit-testable without mocking Dash.
  - `status_cache.py` — Accumulates unique sockets/services across polls.
  - `modal.py`, `keyboard.py`, `menu.py`, `poll.py` — State transition functions.

- **`ui/`** — Rendering helpers that produce Dash components.
  - `map_view.py` — Plotly choropleth map figure.
  - `modal_view.py`, `cache_view.py` — Modal and table content builders.
  - `layout_view.py` — Main layout structure.

- **`assets/`** — Frontend: `styles.css` (dark theme, `#00ff66` accent), `keys.js` (keyboard event handler).

### Platform backends

macOS uses `lsof`, Windows/Linux use `psutil`. The `NetInfoBackend` protocol in `netinfo.py` abstracts this. Docker requires `--network host --pid host`.

## Conventions

- **Python 3.10+** — Uses `match` statements, modern type hints, `from __future__ import annotations`.
- **Ruff** — Line length 100, Google-style docstrings. Rules: `E, F, I, B, UP, SIM, RUF, D`.
- **TypedDict payloads** — `CacheItem`, `OpenPort`, `SnapshotPayload` for structured data between layers.
- **Data directory** — Platform-specific (`~/Library/Application Support/TapMap` on macOS, `%APPDATA%\TapMap` on Windows, `~/.local/share/TapMap` on Linux). Must contain `GeoLite2-City.mmdb` and `GeoLite2-ASN.mmdb`.

## Environment Variables

```
TAPMAP_PORT       — Override server port (default 8050)
TAPMAP_HOST       — Override bind host (default 127.0.0.1)
TAPMAP_DATA_DIR   — Override data directory path
TAPMAP_IN_DOCKER  — Signal Docker mode (sets host to 0.0.0.0)

MAXMIND_ACCOUNT_ID            — MaxMind account ID (enables auto-update)
MAXMIND_LICENSE_KEY           — MaxMind license key (enables auto-update)
MAXMIND_UPDATE_INTERVAL_DAYS  — Refresh cadence in days (default 7)
```

When `MAXMIND_ACCOUNT_ID` and `MAXMIND_LICENSE_KEY` are set, TapMap automatically
downloads and refreshes `GeoLite2-City.mmdb` and `GeoLite2-ASN.mmdb` into the data
directory on startup and on the configured interval. Without credentials, databases
must be placed manually as before.
