"""Corridor weather grid and hourly heatmap frames (SPEC section 4.8).

The grid covers the area within ``CORRIDOR_RADIUS_M`` of any route. Its points sit on a
lattice whose spacing starts at 0.1 degrees (the resolution of the weather cache keys) and
doubles until at most ``MAX_GRID_POINTS`` points remain, so every point stays on a cache key.
"""

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from planner.domain.geometry import METERS_PER_DEGREE, ProximityIndex
from planner.domain.models import HourlySeries, LatLon, RiskLevel
from planner.domain.risk import WindBasis, assess
from planner.domain.weather_select import select_weather

CORRIDOR_RADIUS_M = 25_000.0
MAX_GRID_POINTS = 200
START_SPACING_DEG = 0.1
# Route points used for the mask are this far apart; the mask can miss a point only in a
# band a few meters wide at the edge of the corridor.
MASK_SPACING_M = 2_000.0
FRAME_COUNT = 49
MAX_LATITUDE_DEG = 90.0
MAX_LONGITUDE_DEG = 180.0
MAX_BUFFER_LATITUDE_DEG = 89.0
# Lattice coordinates are rounded to this many decimals so 3 * 0.1 is 0.3, not 0.30000000000000004.
COORDINATE_DECIMALS = 6


@dataclass(frozen=True, slots=True)
class CorridorGrid:
    """Lattice points inside the corridor, ordered by latitude then longitude."""

    spacing_deg: float
    points: tuple[LatLon, ...]


@dataclass(frozen=True, slots=True)
class CorridorFrame:
    """The corridor at one hour, as columns aligned with ``CorridorGrid.points``.

    ``risk`` holds the ``RiskLevel`` value, with -1 for unknown. ``wind_mph`` is the wind
    used for the risk (sustained or gust, per the wind basis); a value is ``None`` when
    the weather there is unavailable.
    """

    time: datetime
    risk: tuple[int, ...]
    wind_mph: tuple[float | None, ...]
    rain_in_hr: tuple[float | None, ...]
    snow_in_hr: tuple[float | None, ...]


def build_grid(routes: Sequence[Sequence[LatLon]]) -> CorridorGrid:
    """Build the corridor grid around ``routes`` with at most ``MAX_GRID_POINTS`` points."""
    if not routes or any(len(route) == 0 for route in routes):
        msg = "every route needs at least one point"
        raise ValueError(msg)

    all_points = [point for route in routes for point in route]
    buffer_lat = CORRIDOR_RADIUS_M / METERS_PER_DEGREE
    max_abs_lat = min(
        max(abs(point.lat) for point in all_points) + buffer_lat, MAX_BUFFER_LATITUDE_DEG
    )
    buffer_lon = buffer_lat / math.cos(math.radians(max_abs_lat))
    bounds = (
        max(min(point.lat for point in all_points) - buffer_lat, -MAX_LATITUDE_DEG),
        min(max(point.lat for point in all_points) + buffer_lat, MAX_LATITUDE_DEG),
        max(min(point.lon for point in all_points) - buffer_lon, -MAX_LONGITUDE_DEG),
        min(max(point.lon for point in all_points) + buffer_lon, MAX_LONGITUDE_DEG),
    )
    index = ProximityIndex(routes, CORRIDOR_RADIUS_M, MASK_SPACING_M)

    spacing = START_SPACING_DEG
    while True:
        points = _masked_lattice(bounds, spacing, index)
        if points is not None:
            return CorridorGrid(spacing_deg=spacing, points=tuple(points))
        spacing *= 2


def build_frames(
    series: Sequence[HourlySeries | None],
    departure: datetime,
    load_lb: float,
    wind_basis: WindBasis = WindBasis.SUSTAINED,
    hours: int = FRAME_COUNT,
) -> list[CorridorFrame]:
    """Assess every grid point for ``hours`` hourly frames from ``floor_hour(departure)``.

    ``series`` holds the hourly weather of each grid point, in grid order; ``None`` marks a
    point without weather, which is reported as unknown.
    """
    if departure.tzinfo is None:
        msg = "departure must be timezone-aware"
        raise ValueError(msg)
    first = departure.replace(minute=0, second=0, microsecond=0)
    return [
        _frame(series, first + timedelta(hours=hour), load_lb, wind_basis) for hour in range(hours)
    ]


def _frame(
    series: Sequence[HourlySeries | None], time: datetime, load_lb: float, wind_basis: WindBasis
) -> CorridorFrame:
    risk: list[int] = []
    wind: list[float | None] = []
    rain: list[float | None] = []
    snow: list[float | None] = []
    for point_series in series:
        if point_series is None:
            risk.append(int(RiskLevel.UNKNOWN))
            wind.append(None)
            rain.append(None)
            snow.append(None)
            continue
        sample = select_weather(point_series, time)
        risk.append(int(assess(sample, load_lb, wind_basis).level))
        wind.append(sample.gust_mph if wind_basis is WindBasis.GUST else sample.wind_mph)
        rain.append(sample.rain_in_hr)
        snow.append(sample.snow_in_hr)
    return CorridorFrame(
        time=time,
        risk=tuple(risk),
        wind_mph=tuple(wind),
        rain_in_hr=tuple(rain),
        snow_in_hr=tuple(snow),
    )


def _masked_lattice(
    bounds: tuple[float, float, float, float], spacing: float, index: ProximityIndex
) -> list[LatLon] | None:
    """Lattice points in the corridor, or ``None`` as soon as there are too many."""
    points: list[LatLon] = []
    for candidate in _lattice(bounds, spacing):
        if index.is_near(candidate):
            points.append(candidate)
            if len(points) > MAX_GRID_POINTS:
                return None
    return points


def _lattice(bounds: tuple[float, float, float, float], spacing: float) -> Iterator[LatLon]:
    """Points on multiples of ``spacing`` inside the bounds, by latitude then longitude."""
    min_lat, max_lat, min_lon, max_lon = bounds
    lons = [
        round(col * spacing, COORDINATE_DECIMALS)
        for col in range(math.ceil(min_lon / spacing), math.floor(max_lon / spacing) + 1)
    ]
    for row in range(math.ceil(min_lat / spacing), math.floor(max_lat / spacing) + 1):
        lat = round(row * spacing, COORDINATE_DECIMALS)
        for lon in lons:
            yield LatLon(lat, lon)
