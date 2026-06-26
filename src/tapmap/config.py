"""Define application configuration for TapMap.

Edit this file to adjust basic behavior without modifying application code.
"""

from __future__ import annotations

from typing import Final, Literal

LocationMode = Literal["auto", "none"]

SERVER_PORT: Final[int] = 8050
"""HTTP port used by the local Dash server."""

LAUNCH_BROWSER: Final[bool] = True
"""Open the default web browser automatically at startup."""

CACHE_RETENTION_MIN: Final[int] = 0
"""Keep cached connections until Clear cache.

0 disables automatic cache expiration.
"""

MY_LOCATION: Final[tuple[float, float] | LocationMode] = "auto"
"""Local map marker options:
- (lon, lat): fixed manual coordinates
- "auto": approximate location based on public IP
- "none": disable local marker
"""

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
