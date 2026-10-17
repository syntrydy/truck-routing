"""Immutable value objects shared by the pure domain modules.

Units: distances in miles unless a name says otherwise, speeds in mph, precipitation
in inches per hour, durations in seconds, all datetimes timezone-aware (UTC).
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum

MIN_LATITUDE = -90.0
MAX_LATITUDE = 90.0
MIN_LONGITUDE = -180.0
MAX_LONGITUDE = 180.0


class RiskLevel(IntEnum):
    """Ordered risk level of a weather factor, checkpoint, stretch or route.

    ``UNKNOWN`` is a sentinel for "no usable weather data", not a level: it has no
    place in the ordering. Its value (-1) matches the heatmap wire format, but
    comparing it with ``<``/``>`` is meaningless. Use ``is_known`` and ``max_known``.
    """

    UNKNOWN = -1
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4


def is_known(level: RiskLevel) -> bool:
    """Return whether ``level`` is a real level rather than the UNKNOWN sentinel."""
    return level is not RiskLevel.UNKNOWN


def max_known(levels: Iterable[RiskLevel]) -> RiskLevel:
    """Return the highest known level, ignoring UNKNOWN.

    Returns ``RiskLevel.UNKNOWN`` when there is no known level (empty input or all
    UNKNOWN), so unknown data can never be mistaken for ``LOW``.
    """
    known = [level for level in levels if is_known(level)]
    return max(known, default=RiskLevel.UNKNOWN)


@dataclass(frozen=True, slots=True)
class LatLon:
    """A WGS84 coordinate in decimal degrees."""

    lat: float
    lon: float

    def __post_init__(self) -> None:
        if not MIN_LATITUDE <= self.lat <= MAX_LATITUDE:
            msg = f"latitude {self.lat} outside [{MIN_LATITUDE}, {MAX_LATITUDE}]"
            raise ValueError(msg)
        if not MIN_LONGITUDE <= self.lon <= MAX_LONGITUDE:
            msg = f"longitude {self.lon} outside [{MIN_LONGITUDE}, {MAX_LONGITUDE}]"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class WeatherSample:
    """Weather at one place and time. ``None`` means the value is unavailable.

    ``wind_mph`` is the sustained 10 m wind, ``gust_mph`` the 10 m gust,
    ``rain_in_hr`` is rain plus showers and ``snow_in_hr`` is snowfall.
    """

    wind_mph: float | None = None
    gust_mph: float | None = None
    rain_in_hr: float | None = None
    snow_in_hr: float | None = None
    weather_code: int | None = None


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """A sampled point along a route with its estimated arrival time.

    ``distance_mi`` is the cumulative distance from the origin. ``level`` and
    ``reasons`` are filled in once the weather at ``eta`` has been assessed.
    """

    index: int
    location: LatLon
    distance_mi: float
    eta: datetime
    weather: WeatherSample | None = None
    level: RiskLevel = RiskLevel.UNKNOWN
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.eta.tzinfo is None:
            msg = "checkpoint eta must be timezone-aware"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Stretch:
    """The part of a route owned by one checkpoint, up to the next checkpoint."""

    start_index: int
    end_index: int
    length_mi: float
    level: RiskLevel


@dataclass(frozen=True, slots=True)
class RouteScore:
    """Aggregated risk of a route (SPEC section 4.6).

    ``avg_risk`` is the distance-weighted mean of the known stretch levels (0-4),
    or ``None`` when no stretch is known. ``miles_by_level`` only counts known
    levels; ``unknown_miles`` is reported separately and never counted as LOW.
    """

    distance_mi: float
    duration_s: float
    miles_by_level: Mapping[RiskLevel, float] = field(default_factory=dict)
    unknown_miles: float = 0.0
    avg_risk: float | None = None
    worst_level: RiskLevel = RiskLevel.UNKNOWN
    low_confidence: bool = False


@dataclass(frozen=True, slots=True)
class HourlySeries:
    """Hourly weather at one place: entry ``i`` describes ``start + i`` hours.

    ``start`` is a timezone-aware instant on the hour. All tuples have the same length
    and ``None`` marks a value the provider did not supply. Precipitation values
    (``rain_in``, ``showers_in``, ``snowfall_in``, in inches) are totals over the hour
    ending at the entry's time; wind and gusts (mph) are instantaneous.
    """

    start: datetime
    wind_mph: tuple[float | None, ...]
    gust_mph: tuple[float | None, ...]
    rain_in: tuple[float | None, ...]
    showers_in: tuple[float | None, ...]
    snowfall_in: tuple[float | None, ...]
    weather_code: tuple[int | None, ...]

    def __post_init__(self) -> None:
        if self.start.tzinfo is None:
            msg = "series start must be timezone-aware"
            raise ValueError(msg)
        if self.start != self.start.replace(minute=0, second=0, microsecond=0):
            msg = "series start must be on the hour"
            raise ValueError(msg)
        lengths = {
            len(self.wind_mph),
            len(self.gust_mph),
            len(self.rain_in),
            len(self.showers_in),
            len(self.snowfall_in),
            len(self.weather_code),
        }
        if len(lengths) != 1:
            msg = "all hourly series must have the same length"
            raise ValueError(msg)

    def __len__(self) -> int:
        return len(self.wind_mph)

    @property
    def end(self) -> datetime:
        """Time of the last entry."""
        return self.start + timedelta(hours=len(self) - 1)
