"""Define Plotly map rendering for TapMap.

Build a dark-themed world map with:
- a base choropleth layer
- connection lines from a "my location" marker when enabled
- target markers with hover summaries
"""

from __future__ import annotations

import logging
from typing import Final, TypeAlias

import plotly.graph_objects as go

LonLat: TypeAlias = tuple[float, float]
PointSets: TypeAlias = tuple[list[LonLat], list[LonLat]]  # (targets, my_location)
CustomData: TypeAlias = dict[str, object]


class MapUI:
    """Build Plotly figures for the TapMap UI."""

    COUNTRY_CODES: Final[tuple[str, ...]] = (
        "AFG",
        "ALB",
        "DZA",
        "AND",
        "AGO",
        "ATG",
        "ARG",
        "ARM",
        "AUS",
        "AUT",
        "AZE",
        "BHS",
        "BHR",
        "BGD",
        "BRB",
        "BLR",
        "BEL",
        "BLZ",
        "BEN",
        "BTN",
        "BOL",
        "BIH",
        "BWA",
        "BRA",
        "BRN",
        "BGR",
        "BFA",
        "BDI",
        "KHM",
        "CMR",
        "CAN",
        "CPV",
        "CAF",
        "TCD",
        "CHL",
        "CHN",
        "COL",
        "COM",
        "COD",
        "COG",
        "CRI",
        "CIV",
        "HRV",
        "CUB",
        "CYP",
        "CZE",
        "DNK",
        "DJI",
        "DMA",
        "DOM",
        "ECU",
        "EGY",
        "SLV",
        "GNQ",
        "ERI",
        "EST",
        "SWZ",
        "ETH",
        "FJI",
        "FIN",
        "FRA",
        "GAB",
        "GMB",
        "GEO",
        "DEU",
        "GHA",
        "GRC",
        "GRD",
        "GTM",
        "GIN",
        "GNB",
        "GUY",
        "HTI",
        "HND",
        "HUN",
        "ISL",
        "IND",
        "IDN",
        "IRN",
        "IRQ",
        "IRL",
        "ISR",
        "ITA",
        "JAM",
        "JPN",
        "JOR",
        "KAZ",
        "KEN",
        "KIR",
        "PRK",
        "KOR",
        "KWT",
        "KGZ",
        "LAO",
        "LVA",
        "LBN",
        "LSO",
        "LBR",
        "LBY",
        "LIE",
        "LTU",
        "LUX",
        "MDG",
        "MWI",
        "MYS",
        "MDV",
        "MLI",
        "MLT",
        "MHL",
        "MRT",
        "MUS",
        "MEX",
        "FSM",
        "MDA",
        "MCO",
        "MNG",
        "MNE",
        "MAR",
        "MOZ",
        "MMR",
        "NAM",
        "NRU",
        "NPL",
        "NLD",
        "NZL",
        "NIC",
        "NER",
        "NGA",
        "MKD",
        "NOR",
        "OMN",
        "PAK",
        "PLW",
        "PAN",
        "PNG",
        "PRY",
        "PER",
        "PHL",
        "POL",
        "PRT",
        "QAT",
        "ROU",
        "RUS",
        "RWA",
        "KNA",
        "LCA",
        "VCT",
        "WSM",
        "SMR",
        "STP",
        "SAU",
        "SEN",
        "SRB",
        "SYC",
        "SLE",
        "SGP",
        "SVK",
        "SVN",
        "SLB",
        "SOM",
        "ZAF",
        "SSD",
        "ESP",
        "LKA",
        "SDN",
        "SUR",
        "SWE",
        "CHE",
        "SYR",
        "TWN",
        "TJK",
        "TZA",
        "THA",
        "TLS",
        "TGO",
        "TON",
        "TTO",
        "TUN",
        "TUR",
        "TKM",
        "TUV",
        "UGA",
        "UKR",
        "ARE",
        "GBR",
        "USA",
        "URY",
        "UZB",
        "VUT",
        "VAT",
        "VEN",
        "VNM",
        "YEM",
        "ZMB",
        "ZWE",
        "GRL",
        "ATA",
        "CXR",
        "CCK",
        "FRO",
        "GLP",
        "GUF",
        "MTQ",
        "MYT",
        "REU",
        "SHN",
        "SPM",
        "WLF",
        "ALA",
        "BES",
        "CUW",
        "CYM",
    )
    VALUES: Final[tuple[int, ...]] = (1,) * len(COUNTRY_CODES)

    COLOR_NORMAL: Final[str] = "#FF00FF"
    COLOR_ME: Final[str] = "#00FFFF"
    COLOR_ZOOM: Final[str] = "#FFFF00"

    HOVER_BG: Final[str] = "#000000"
    HOVER_BORDER: Final[str] = "#00aa44"
    HOVER_FONT: Final[str] = "#00ff66"

    EARTH_RADIUS_KM: Final[float] = 6371.0

    def __init__(self, *, zoom_near_km: float, debug: bool = False) -> None:
        self.zoom_near_km = zoom_near_km
        self.debug = debug
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _cd_target(idx: int) -> CustomData:
        return {"kind": "target", "idx": idx}

    @staticmethod
    def _cd_line(idx: int) -> CustomData:
        return {"kind": "line", "idx": idx}

    @staticmethod
    def _cd_me() -> CustomData:
        return {"kind": "me"}

    @staticmethod
    def _haversine_km(a: LonLat, b: LonLat, radius_km: float) -> float:
        """Compute great-circle distance between two (lon, lat) points in kilometers."""
        import math

        lon1, lat1 = a
        lon2, lat2 = b

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlat_rad = math.radians(lat2 - lat1)
        dlon_rad = math.radians(lon2 - lon1)

        sin_dlat = math.sin(dlat_rad / 2.0)
        sin_dlon = math.sin(dlon_rad / 2.0)

        h = sin_dlat * sin_dlat + math.cos(lat1_rad) * math.cos(lat2_rad) * sin_dlon * sin_dlon
        return 2.0 * radius_km * math.asin(min(1.0, math.sqrt(h)))

    def create_figure(
        self,
        point_sets: PointSets,
        summaries: dict[str, str] | None = None,
    ) -> go.Figure:
        """Build a world map figure.

        Color rules:
            - MAGENTA: normal remote targets and lines
            - YELLOW: targets and lines with nearby neighbors (zoom recommended)
            - CYAN: local marker when enabled
        """
        summaries = summaries or {}
        targets, my_location = point_sets

        fig = go.Figure()

        fig.add_trace(
            go.Choropleth(
                locations=self.COUNTRY_CODES,
                z=self.VALUES,
                showscale=False,
                colorscale=[[0, "#00AA00"], [1, "#00AA00"]],
                marker_line_color="#66FF66",
                marker_line_width=0.5,
                hoverinfo="skip",
                showlegend=False,
                name="world",
            )
        )

        my_lon: float | None = None
        my_lat: float | None = None
        if my_location:
            my_lon, my_lat = my_location[0]

        zoom_flags = [False] * len(targets)
        for i in range(len(targets)):
            for j in range(i + 1, len(targets)):
                if (
                    self._haversine_km(
                        targets[i],
                        targets[j],
                        radius_km=self.EARTH_RADIUS_KM,
                    )
                    <= self.zoom_near_km
                ):
                    zoom_flags[i] = True
                    zoom_flags[j] = True

        if targets and my_lon is not None and my_lat is not None:
            for i, (lon, lat) in enumerate(targets):
                line_color = self.COLOR_ZOOM if zoom_flags[i] else self.COLOR_NORMAL
                fig.add_trace(
                    go.Scattergeo(
                        lon=[my_lon, lon],
                        lat=[my_lat, lat],
                        mode="lines",
                        line=dict(width=3, color=line_color),
                        showlegend=False,
                        hoverinfo="skip",
                        hovertemplate=None,
                        customdata=[self._cd_line(i), self._cd_line(i)],
                        name=f"line_{i}",
                    )
                )

        if targets:
            lons = [lon for lon, _ in targets]
            lats = [lat for _, lat in targets]

            if self.debug:
                unique_xy = len(set(zip(lons, lats, strict=False)))
                self.logger.debug("Figure targets: count=%s unique_xy=%s", len(lons), unique_xy)

            colors: list[str] = []
            texts: list[str] = []
            for i in range(len(targets)):
                colors.append(self.COLOR_ZOOM if zoom_flags[i] else self.COLOR_NORMAL)
                base = summaries.get(str(i), f"Summary {i}")
                texts.append(base)

            fig.add_trace(
                go.Scattergeo(
                    lon=lons,
                    lat=lats,
                    mode="markers",
                    marker=dict(
                        size=10, color=colors, symbol="circle", line=dict(width=0), opacity=1.0
                    ),
                    showlegend=False,
                    hovertemplate="%{text}<extra></extra>",
                    text=texts,
                    customdata=[self._cd_target(i) for i in range(len(targets))],
                    name="targets",
                )
            )


        if my_lon is not None and my_lat is not None:
            fig.add_trace(
                go.Scattergeo(
                    lon=[my_lon],
                    lat=[my_lat],
                    mode="markers",
                    marker=dict(size=10, color=self.COLOR_ME, symbol="circle", opacity=1.0),
                    hoverinfo="skip",
                    hovertemplate=None,
                    showlegend=False,
                    customdata=[self._cd_me()],
                    name="me",
                )
            )

        fig.update_geos(
            visible=True,
            projection_type="natural earth",
            showframe=False,
            showcountries=False,
            showcoastlines=False,
            showland=False,
            showlakes=True,
            lakecolor="black",
            bgcolor="black",
            uirevision="keep",
        )

        font_family = (
            "ui-monospace, SFMono-Regular, Menlo, Consolas, "
            "'Liberation Mono', 'Courier New', monospace"
        )
        fig.update_layout(
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="black",
            plot_bgcolor="black",
            showlegend=False,
            clickmode="event",
            hovermode="closest",
            dragmode="pan",
            uirevision="keep",
            hoverlabel=dict(
                bgcolor=self.HOVER_BG,
                bordercolor=self.HOVER_BORDER,
                font=dict(
                    color=self.HOVER_FONT,
                    family=font_family,
                    size=14,
                ),
            ),
        )

        return fig
