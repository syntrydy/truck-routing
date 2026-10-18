"""Hourly weather from the US National Weather Service (api.weather.gov), the fallback source.

Two calls per place: ``/points/{lat},{lon}`` names the forecast grid cell the place is in, and
the cell's raw forecast holds wind, gusts, liquid precipitation and snowfall as values over
intervals of one to six hours. They are converted here, in one place, to the hourly mph and
inches-per-hour series the domain uses, in the same convention as the Open-Meteo adapter: a
precipitation value at hour ``h`` covers the hour before ``h``.

The NWS covers the United States only; a place it does not cover has no weather (``None``).
"""

import logging
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from datetime import UTC, date, datetime
from typing import Any

from planner.domain.models import HourlySeries, LatLon
from planner.infra.cache import StaleIfErrorCache, nws_grid_key, nws_weather_key
from planner.infra.errors import UpstreamError
from planner.infra.http import UpstreamClient
from planner.infra.resilience import Deadline, current_deadline
from planner.providers.jsonshape import JsonShape
from planner.providers.protocols import WeatherResult, rounded_point

logger = logging.getLogger(__name__)

NAME = "nws"
DEFAULT_BASE_URL = "https://api.weather.gov"
EXPECTED_UNITS = {
    "windSpeed": "wmoUnit:km_h-1",
    "windGust": "wmoUnit:km_h-1",
    "quantitativePrecipitation": "wmoUnit:mm",
    "snowfallAmount": "wmoUnit:mm",
}
MAX_CONCURRENT_PLACES = 16
FRESH_TTL_S = 30 * 60
MAX_STALE_AGE_S = 6 * 60 * 60
GRID_TTL_S = 7 * 24 * 60 * 60  # which grid cell a place is in does not change
MAX_DAYS = 8  # the forecast horizon of the grid data
HOURS_PER_DAY = 24
SECONDS_PER_HOUR = 3_600
KM_PER_MILE = 1.609344
MM_PER_INCH = 25.4
# Snow melts to about a tenth of its depth. Precipitation totals include that melt, so it is taken
# out to leave the rain: otherwise snow would also be counted as rain.
SNOW_TO_LIQUID_RATIO = 10.0
MAX_REASONS_LOGGED = 3

_shape = JsonShape(NAME)
_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?)?$")


class NwsWeatherProvider:
    """Hourly weather from the NWS through the resilient upstream client and the cache."""

    name = NAME

    def __init__(
        self, client: UpstreamClient, cache: StaleIfErrorCache, base_url: str = DEFAULT_BASE_URL
    ) -> None:
        self._client = client
        self._cache = cache
        self._base_url = base_url.rstrip("/")

    def hourly(self, points: Sequence[LatLon], first_day: date, last_day: date) -> WeatherResult:
        if last_day < first_day:
            msg = "last day is before the first day"
            raise ValueError(msg)
        if (last_day - first_day).days >= MAX_DAYS:
            msg = f"at most {MAX_DAYS} days can be requested"
            raise ValueError(msg)

        places = list(dict.fromkeys(rounded_point(point) for point in points))
        series: dict[LatLon, HourlySeries | None] = {}
        old: dict[LatLon, HourlySeries] = {}  # past their fresh lifetime, usable if a fetch fails
        to_fetch: list[LatLon] = []
        for place in places:
            entry = self._cache.peek(nws_weather_key(place, first_day, last_day))
            if entry is not None and entry.age_s < FRESH_TTL_S:
                series[place] = entry.value
                continue
            to_fetch.append(place)
            if entry is not None and entry.age_s < MAX_STALE_AGE_S:
                old[place] = entry.value

        stale = False
        for place, fetched in self._fetch_places(to_fetch, first_day, last_day).items():
            if fetched is not None:
                series[place] = fetched
                self._cache.put(
                    nws_weather_key(place, first_day, last_day),
                    fetched,
                    max_stale_age_s=MAX_STALE_AGE_S,
                )
            elif place in old:  # the provider is failing: fall back on what the cache still has
                series[place] = old[place]
                stale = True
        return WeatherResult(
            series={place: series.get(place) for place in places},
            source=NAME,
            stale=stale,
            missing=sum(1 for place in places if series.get(place) is None),
        )

    def _fetch_places(
        self, places: Sequence[LatLon], first_day: date, last_day: date
    ) -> dict[LatLon, HourlySeries | None]:
        """Fetch the places in the order given, a few at a time.

        A place that cannot be had (an outage, a place outside the NWS's area, an unusable
        answer, or no time left) is ``None``; the reasons are logged together, once. Places
        are fetched in order so that, if time runs out, the first ones asked for are the ones
        that have weather.
        """
        if not places:
            return {}
        deadline = current_deadline()  # worker threads do not inherit the caller's context
        lost: Counter[str] = Counter()
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_PLACES) as pool:
            futures = {
                place: pool.submit(
                    copy_context().run, self._fetch_place, place, first_day, last_day, deadline
                )
                for place in places
            }
            fetched: dict[LatLon, HourlySeries | None] = {}
            for place, future in futures.items():
                try:
                    fetched[place] = future.result()
                except UpstreamError as error:  # a fallback must not turn a gap into an error
                    lost[error.message] += 1
                    fetched[place] = None
        if lost:
            reasons = "; ".join(
                f"{count} x {reason}" for reason, count in lost.most_common(MAX_REASONS_LOGGED)
            )
            logger.warning(
                "nws lost weather for %d of %d places: %s", sum(lost.values()), len(places), reasons
            )
        return fetched

    def _fetch_place(
        self, place: LatLon, first_day: date, last_day: date, deadline: Deadline | None
    ) -> HourlySeries | None:
        grid_url = self._grid_url(place, deadline)
        payload = self._client.get_json(NAME, grid_url, deadline=deadline)
        properties = _shape.mapping(
            _shape.mapping(payload, "forecast").get("properties"), "forecast"
        )
        return convert_grid(properties, first_day, last_day)

    def _grid_url(self, place: LatLon, deadline: Deadline | None) -> str:
        key = nws_grid_key(place)
        entry = self._cache.peek(key)
        if entry is not None and entry.age_s < GRID_TTL_S:
            return str(entry.value)
        payload = self._client.get_json(
            NAME, f"{self._base_url}/points/{place.lat:.1f},{place.lon:.1f}", deadline=deadline
        )
        properties = _shape.mapping(_shape.mapping(payload, "point").get("properties"), "point")
        url = properties.get("forecastGridData")
        if not isinstance(url, str) or not url.startswith(f"{self._base_url}/"):
            raise _shape.error("the point does not name a forecast grid on api.weather.gov")
        self._cache.put(key, url, max_stale_age_s=GRID_TTL_S)
        return url


def convert_grid(
    properties: Mapping[str, Any], first_day: date, last_day: date
) -> HourlySeries | None:
    """Hourly series for the UTC days ``first_day`` to ``last_day`` from a grid forecast.

    Hours the forecast does not cover are ``None`` (unknown). ``None`` as a whole means the
    forecast has no wind at all for those days. Raises ``UpstreamContractError`` for units
    other than the agreed ones, never converting them silently.
    """
    start = datetime(first_day.year, first_day.month, first_day.day, tzinfo=UTC)
    hours = ((last_day - first_day).days + 1) * HOURS_PER_DAY

    def column(name: str, *, amount: bool) -> list[float | None]:
        variable = _shape.mapping(properties.get(name), name)
        if variable.get("uom") != EXPECTED_UNITS[name]:
            raise _shape.error(
                f"{name} is in {variable.get('uom')!r}, expected {EXPECTED_UNITS[name]!r}"
            )
        # An amount over an interval is spread evenly over its hours and, as a value at hour h
        # covers the hour before h, placed one hour later; a speed holds from the interval's start.
        return _spread(_shape.sequence(variable.get("values"), name), start, hours, amount=amount)

    wind = column("windSpeed", amount=False)
    gust = column("windGust", amount=False)
    precipitation = column("quantitativePrecipitation", amount=True)
    snow = column("snowfallAmount", amount=True)
    if all(value is None for value in wind):
        return None

    rain: list[float | None] = []
    for liquid_mm, snow_mm in zip(precipitation, snow, strict=True):
        if liquid_mm is None:
            rain.append(None)
        else:
            melt_mm = (snow_mm or 0.0) / SNOW_TO_LIQUID_RATIO
            rain.append(max(0.0, liquid_mm - melt_mm) / MM_PER_INCH)
    return HourlySeries(
        start=start,
        wind_mph=tuple(_scaled(value, 1 / KM_PER_MILE) for value in wind),
        gust_mph=tuple(_scaled(value, 1 / KM_PER_MILE) for value in gust),
        rain_in=tuple(rain),
        showers_in=tuple(None if value is None else 0.0 for value in rain),
        snowfall_in=tuple(_scaled(value, 1 / MM_PER_INCH) for value in snow),
        weather_code=(None,) * hours,
    )


def _scaled(value: float | None, factor: float) -> float | None:
    return None if value is None else value * factor


def _spread(
    values: Sequence[Any], start: datetime, hours: int, *, amount: bool
) -> list[float | None]:
    """One entry per hour from ``start``: each interval's value, or its share if it is an amount."""
    hourly: list[float | None] = [None] * hours
    shift = 1 if amount else 0
    for item in values:
        entry = _shape.mapping(item, "value")
        begin_text, _, span = str(entry.get("validTime")).partition("/")
        begin = _begin(begin_text)
        length = _duration_hours(span)
        number = _shape.optional_number(entry.get("value"), "value")
        first = int((begin - start).total_seconds() // SECONDS_PER_HOUR)
        for offset in range(length):
            index = first + offset + shift
            if 0 <= index < hours:
                hourly[index] = None if number is None else number / length if amount else number
    return hourly


def _begin(text: str) -> datetime:
    try:
        begin = datetime.fromisoformat(text)
    except ValueError as error:
        raise _shape.error("a validTime does not start with a date and time") from error
    if begin.tzinfo is None or begin.minute or begin.second:
        raise _shape.error("a validTime does not start on the hour in a known zone")
    return begin.astimezone(UTC)


def _duration_hours(text: str) -> int:
    match = _DURATION.match(text)
    if match is None or not any(match.groups()):
        raise _shape.error("a validTime has no usable duration")
    days, hours = (int(group or 0) for group in match.groups())
    return days * HOURS_PER_DAY + hours
