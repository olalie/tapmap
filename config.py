"""
Configuration for TapMap.

Users can edit this file to adjust basic behavior without modifying
the application code.
"""

from __future__ import annotations

from typing import Final, Literal

# ---------------------------------------------------------------------
# Local map marker
# ---------------------------------------------------------------------

LocationMode = Literal["auto", "none"]

# Local map marker:
# - (lon, lat): fixed manual location
# - "auto": approximate location based on public IP
# - "none": no local marker
# MY_LOCATION: Final[tuple[float, float] | LocationMode] = (11.3421, 59.5950)
MY_LOCATION: Final[tuple[float, float] | LocationMode] = "auto"
# MY_LOCATION: Final[tuple[float, float] | LocationMode] = "none"


# ---------------------------------------------------------------------
# Polling and map behavior
# ---------------------------------------------------------------------

# Snapshot interval in milliseconds.
POLL_INTERVAL_MS: Final[int] = 5_000

# Decimal precision for grouping endpoints on the map.
# 3 ≈ 100 m precision.
COORD_PRECISION: Final[int] = 3

# Distance threshold for marking endpoints as "nearby".
# Endpoints closer than this distance are shown in yellow.
ZOOM_NEAR_KM: Final[float] = 25.0
