"""Define application configuration for TapMap.

Edit this file to adjust basic behavior without modifying application code.
"""

from __future__ import annotations

from typing import Final, Literal

# Configure local map marker behavior.
LocationMode = Literal["auto", "none"]

# Configure local Dash server.
SERVER_PORT: Final[int] = 8050
"""HTTP port used by the local Dash server."""

MY_LOCATION: Final[tuple[float, float] | LocationMode] = "auto"
"""Local map marker options:
- (lon, lat): fixed manual coordinates
- "auto": approximate location based on public IP
- "none": disable local marker
"""

# Configure polling interval and map behavior.
POLL_INTERVAL_MS: Final[int] = 5_000
"""Interval between model snapshots and cache updates."""

COORD_PRECISION: Final[int] = 3
"""Decimal precision used when grouping services into map markers.

3 corresponds to approximately 100 m precision.
"""

ZOOM_NEAR_KM: Final[float] = 25.0
"""Distance threshold in kilometers for marking locations as far.

Locations within this distance are shown in yellow.
"""

# Configure MaxMind GeoLite2 auto-update.
MAXMIND_UPDATE_INTERVAL_DAYS: Final[float] = 7.0
"""Days between automatic GeoLite2 database downloads.

Set MAXMIND_ACCOUNT_ID and MAXMIND_LICENSE_KEY environment variables (or provide
them via Docker / compose) to enable auto-update.  When credentials are absent
the updater is disabled and databases must be placed manually.
"""
