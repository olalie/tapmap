"""Define application configuration for TapMap.

Edit this file to adjust basic behavior without modifying application code.
"""

from __future__ import annotations

from typing import Final, Literal

# Configure local map marker behavior.

LocationMode = Literal["auto", "none"]

# Local map marker options:
# - (lon, lat): fixed manual coordinates
# - "auto": approximate location based on public IP
# - "none": disable local marker
# MY_LOCATION: Final[tuple[float, float] | LocationMode] = (11.3421, 59.5950)
MY_LOCATION: Final[tuple[float, float] | LocationMode] = "auto"
# MY_LOCATION: Final[tuple[float, float] | LocationMode] = "none"


# Configure polling interval and map behavior.

# Interval between model snapshots and cache updates.
POLL_INTERVAL_MS: Final[int] = 5_000

# Decimal precision used when grouping endpoints on the map.
# 3 corresponds to approximately 100 m precision.
COORD_PRECISION: Final[int] = 3

# Distance threshold in kilometers for marking endpoints as nearby.
# Endpoints within this distance are shown in yellow.
ZOOM_NEAR_KM: Final[float] = 25.0
