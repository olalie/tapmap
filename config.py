"""Define application configuration for TapMap.

Edit this file to adjust basic behavior without modifying application code.
"""

from __future__ import annotations

from typing import Final, Literal

# Configure local map marker behavior.

LocationMode = Literal["auto", "none"]


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
