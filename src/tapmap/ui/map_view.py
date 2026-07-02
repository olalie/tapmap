"""Render TapMap world map with country layer, connections and geo points."""

from __future__ import annotations

import math
from typing import Final, TypeAlias

import plotly.graph_objects as go
import pycountry

from .country_info import get_bounds

LonLat: TypeAlias = tuple[float, float]
PointSets: TypeAlias = tuple[list[LonLat], list[LonLat]]  # (geo_points, my_location)
CustomData: TypeAlias = dict[str, object]


class MapUI:
    """Build Plotly map figures for TapMap."""

    COUNTRY_CODES: Final[tuple[str, ...]] = tuple(
        c.alpha_3 for c in pycountry.countries if hasattr(c, "alpha_3")
    )
    VALUES: Final[tuple[int, ...]] = (1,) * len(COUNTRY_CODES)

    COLOR_NORMAL: Final[str] = "#FF00FF"
    COLOR_ME: Final[str] = "#00FFFF"
    COLOR_ZOOM: Final[str] = "#FFFF00"

    HOVER_BG: Final[str] = "#000000"
    HOVER_BORDER: Final[str] = "#00aa44"
    HOVER_FONT: Final[str] = "#00ff66"

    EARTH_RADIUS_KM: Final[float] = 6371.0

    def __init__(self, *, zoom_near_km: float) -> None:
        self.zoom_near_km = zoom_near_km

    @staticmethod
    def _cd_geo_point(idx: int) -> CustomData:
        """Return customdata for a geo point."""
        return {"kind": "geo_point", "idx": idx}

    @staticmethod
    def _cd_line(idx: int) -> CustomData:
        """Return customdata for a connection line."""
        return {"kind": "line", "idx": idx}

    @staticmethod
    def _cd_me() -> CustomData:
        return {"kind": "me"}

    @staticmethod
    def _haversine_km(a: LonLat, b: LonLat, radius_km: float) -> float:
        """Return great-circle distance in kilometers between two (lon, lat) points."""
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

    def _add_world_layer(
        self,
        fig: go.Figure,
        *,
        selected_country: str | None
    ) -> None:
        """Add world layer. Highlight selected country when provided."""
        line_colors = ["#66FF66"] * len(self.COUNTRY_CODES)
        line_widths = [0.5] * len(self.COUNTRY_CODES)

        if isinstance(selected_country, str):
            country_code = selected_country

            try:
                iso3 = pycountry.countries.get(alpha_2=country_code.upper()).alpha_3
                idx = self.COUNTRY_CODES.index(iso3)
                line_colors[idx] = "white"
                line_widths[idx] = 3
            except Exception:
                pass

        fig.add_trace(
            go.Choropleth(
                locations=self.COUNTRY_CODES,
                z=self.VALUES,
                showscale=False,
                colorscale=[[0, "#00AA00"], [1, "#00AA00"]],
                marker_line_color=line_colors,
                marker_line_width=line_widths,
                hoverinfo="skip",
                showlegend=False,
                name="world",
            )
        )

    def _compute_zoom_flags(self, geo_points: list[LonLat]) -> list[bool]:
        """Return flags for geo_points with neighbors within zoom distance."""
        zoom_flags = [False] * len(geo_points)
        for i in range(len(geo_points)):
            for j in range(i + 1, len(geo_points)):
                if (
                    self._haversine_km(
                        geo_points[i],
                        geo_points[j],
                        radius_km=self.EARTH_RADIUS_KM,
                    )
                    <= self.zoom_near_km
                ):
                    zoom_flags[i] = True
                    zoom_flags[j] = True
        return zoom_flags

    def _add_connection_lines(
            self,
            fig: go.Figure,
            *,
            geo_points: list[LonLat],
            my_lon: float,
            my_lat: float,
            zoom_flags: list[bool],
        ) -> None:
        """Add lines from local position to each geo_point."""
        for i, (lon, lat) in enumerate(geo_points):
            line_color = self.COLOR_ZOOM if zoom_flags[i] else self.COLOR_NORMAL
            opacity = 1.0
            fig.add_trace(
                go.Scattergeo(
                    lon=[my_lon, lon],
                    lat=[my_lat, lat],
                    mode="lines",
                    line=dict(width=3, color=line_color),
                    opacity=opacity,
                    showlegend=False,
                    hoverinfo="skip",
                    hovertemplate=None,
                    customdata=[self._cd_line(i), self._cd_line(i)],
                    name=f"line_{i}",
                )
            )

    def _add_geo_point_markers(
        self,
        fig: go.Figure,
        *,
        geo_points: list[LonLat],
        summaries: dict[str, str],
        zoom_flags: list[bool],
    ) -> None:
        """Add markers for geo_points with hover text."""
        lons = [lon for lon, _ in geo_points]
        lats = [lat for _, lat in geo_points]
        colors: list[str] = []
        texts: list[str] = []

        for i in range(len(geo_points)):
            # Color based on proximity
            colors.append(self.COLOR_ZOOM if zoom_flags[i] else self.COLOR_NORMAL)

            # Build hover text for each mapped location.
            base = summaries.get(str(i), f"Summary {i}")
            texts.append(base)

        fig.add_trace(
            go.Scattergeo(
                lon=lons,
                lat=lats,
                mode="markers",
                marker=dict(
                    size=10,
                    color=colors,
                    symbol="circle",
                    opacity=1.0,
                ),
                showlegend=False,
                hovertemplate="%{text}<extra></extra>",
                text=texts,
                customdata=[self._cd_geo_point(i) for i in range(len(geo_points))],
                name="geo_points",
            )
        )

    def _add_my_marker(self, fig: go.Figure, *, my_lon: float, my_lat: float) -> None:
        """Add marker for local position."""
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

    def _apply_geos(
        self,
        fig: go.Figure,
        *,
        geo_points,
        my_location,
        selected_country,
        fit_connections: bool = False,
    ) -> None:
        """Configure map projection and camera."""
        
        def camera_from_bounds(
            min_lon: float, max_lon: float, min_lat: float, max_lat: float,
            *,
            scale_factor: float,
        ) -> tuple[dict[str, float], float]:
            """Return camera center and projection scale for geographic bounds."""
            camera_center = {
                "lon": (min_lon + max_lon) / 2,
                "lat": (min_lat + max_lat) / 2,
            }

            lon_fraction = (max_lon - min_lon) / 360
            lat_fraction = (max_lat - min_lat) / 180

            span = max(lon_fraction, lat_fraction, 1e-6)

            return camera_center, scale_factor / span

        camera_center = None
        camera_scale = None

        # Zoom to include all mapped connections (and my location).
        if fit_connections and geo_points:
            points = list(geo_points)
            points.extend(my_location)

            lons = [lon for lon, _ in points]
            lats = [lat for _, lat in points]

            camera_center, camera_scale = camera_from_bounds(
                min(lons), max(lons), min(lats), max(lats),
                scale_factor=0.95,
            )
        
        # Zoom to the selected country.
        elif isinstance(selected_country, str):
            try:
                min_lon, max_lon, min_lat, max_lat = get_bounds(
                    selected_country.upper()
                )

                camera_center, camera_scale = camera_from_bounds(
                    min_lon, max_lon, min_lat, max_lat,
                    scale_factor=0.50,
                )

            except Exception:
                pass

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
        )

        if camera_center is not None:
            fig.update_geos(
                center=camera_center,
                projection_scale=camera_scale,
            )

    def _apply_layout(self, fig: go.Figure) -> None:
        """Apply layout styling and interaction settings."""
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
            uirevision="constant",
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

    def create_figure(
        self,
        point_sets: PointSets,
        summaries: dict[str, str] | None = None,
        selected_country: str | None = None,
        fit_connections: bool = False,
    ) -> go.Figure:
        """Return map figure with world layer, connections, markers, and layout."""
        summaries = summaries or {}
        geo_points, my_location = point_sets

        fig = go.Figure()

        self._add_world_layer(fig, selected_country=selected_country)

        my_lon: float | None = None
        my_lat: float | None = None
        if my_location:
            my_lon, my_lat = my_location[0]

        zoom_flags = self._compute_zoom_flags(geo_points) if geo_points else []

        if geo_points and my_lon is not None and my_lat is not None:
            self._add_connection_lines(
                fig,
                geo_points=geo_points,
                my_lon=my_lon,
                my_lat=my_lat,
                zoom_flags=zoom_flags,
            )

        if geo_points:
            self._add_geo_point_markers(
                fig,
                geo_points=geo_points,
                summaries=summaries,
                zoom_flags=zoom_flags,
            )

        if my_lon is not None and my_lat is not None:
            self._add_my_marker(fig, my_lon=my_lon, my_lat=my_lat)

        self._apply_geos(
            fig,
            geo_points=geo_points,
            my_location=my_location,
            selected_country=selected_country,
            fit_connections=fit_connections,
        )

        self._apply_layout(fig)

        return fig
