"""Pick the weather that applies at an ETA from an hourly series (SPEC section 4.4).

Precipitation values are totals over the hour *preceding* their timestamp, so the value
at ``ceil_hour(eta)`` describes the hour the truck is in. Wind is instantaneous and is
interpolated linearly between the surrounding hours. Anything outside the series, or
missing in it, stays ``None``: unknown, never zero.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta

from planner.domain.models import HourlySeries, WeatherSample

ONE_HOUR = timedelta(hours=1)
# Rain + showers is rounded so float noise (0.01 + 0.09 = 0.09999999999999999) cannot
# push a value across a band edge. Provider values have at most three decimals.
PRECIPITATION_DECIMALS = 4


def select_weather(series: HourlySeries, eta: datetime) -> WeatherSample:
    """Weather at ``eta``; fields the series cannot answer are ``None``."""
    floor_index, fraction = _locate(series, eta)
    ceil_index = floor_index if fraction == 0 else floor_index + 1

    return WeatherSample(
        wind_mph=_interpolate(series.wind_mph, floor_index, fraction),
        gust_mph=_interpolate(series.gust_mph, floor_index, fraction),
        rain_in_hr=_sum_rain_and_showers(
            _at(series.rain_in, ceil_index), _at(series.showers_in, ceil_index)
        ),
        snow_in_hr=_at(series.snowfall_in, ceil_index),
        weather_code=_at(series.weather_code, ceil_index),
    )


def _locate(series: HourlySeries, eta: datetime) -> tuple[int, float]:
    """Index of ``floor_hour(eta)`` in the series and the fraction of an hour past it."""
    whole_hours, remainder = divmod(eta - series.start, ONE_HOUR)
    return whole_hours, remainder / ONE_HOUR


def _at[T](values: Sequence[T | None], index: int) -> T | None:
    """The value at ``index``, or ``None`` when it is outside the series."""
    if 0 <= index < len(values):
        return values[index]
    return None


def _interpolate(values: Sequence[float | None], floor_index: int, fraction: float) -> float | None:
    """Linear interpolation between ``floor_index`` and the next entry."""
    before = _at(values, floor_index)
    if fraction == 0 or before is None:
        return before
    after = _at(values, floor_index + 1)
    if after is None:
        return None
    return before + (after - before) * fraction


def _sum_rain_and_showers(rain: float | None, showers: float | None) -> float | None:
    if rain is None or showers is None:
        return None
    return round(rain + showers, PRECIPITATION_DECIMALS)
