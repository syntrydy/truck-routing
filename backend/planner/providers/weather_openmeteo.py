"""Open-Meteo weather adapter (SPEC section 4.4).

Weather is requested per place on a 0.1 degree grid, in batches, in the units the risk logic
uses. The adapter checks the units the response reports and refuses to continue on a mismatch:
it never converts silently. Each place's series is cached on its own, so a later request for
overlapping places only fetches what is new, and cached series keep a request alive for a
while when Open-Meteo is down.
"""

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from typing import Any

from planner.domain.models import HourlySeries, LatLon
from planner.infra.cache import StaleIfErrorCache, weather_key
from planner.infra.errors import UpstreamTimeout, UpstreamUnavailable
from planner.infra.http import UpstreamClient
from planner.infra.resilience import Deadline, current_deadline
from planner.providers.jsonshape import JsonShape
from planner.providers.protocols import WeatherResult, rounded_point

NAME = "open-meteo"
DEFAULT_BASE_URL = "https://api.open-meteo.com"
HOURLY_VARIABLES = (
    "wind_speed_10m",
    "wind_gusts_10m",
    "rain",
    "showers",
    "snowfall",
    "weather_code",
)
# Open-Meteo spells miles per hour "mp/h". Anything else means the request was not honoured.
EXPECTED_UNITS = {
    "time": "unixtime",
    "wind_speed_10m": "mp/h",
    "wind_gusts_10m": "mp/h",
    "rain": "inch",
    "showers": "inch",
    "snowfall": "inch",
}
MAX_BATCH_POINTS = 100
MAX_CONCURRENT_BATCHES = 4
FRESH_TTL_S = 30 * 60
MAX_STALE_AGE_S = 6 * 60 * 60
MAX_DAYS = 16  # the forecast horizon of the API
SECONDS_PER_HOUR = 3_600

_shape = JsonShape(NAME)


class OpenMeteoWeatherProvider:
    """Hourly weather from Open-Meteo through the resilient upstream client and the cache."""

    name = NAME

    def __init__(
        self,
        client: UpstreamClient,
        cache: StaleIfErrorCache,
        base_url: str = DEFAULT_BASE_URL,
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
        keys = {place: weather_key(place, first_day, last_day) for place in places}
        series: dict[LatLon, HourlySeries | None] = {}
        old: dict[LatLon, Any] = {}  # entries past their fresh lifetime, usable if a fetch fails
        to_fetch: list[LatLon] = []
        for place in places:
            entry = self._cache.peek(keys[place])
            if entry is not None and entry.age_s < FRESH_TTL_S:
                series[place] = entry.value
                continue
            to_fetch.append(place)
            if entry is not None and entry.age_s < MAX_STALE_AGE_S:
                old[place] = entry.value

        batches = [
            to_fetch[start : start + MAX_BATCH_POINTS]
            for start in range(0, len(to_fetch), MAX_BATCH_POINTS)
        ]
        stale = False
        for batch, fetched in zip(
            batches, self._fetch_batches(batches, first_day, last_day), strict=True
        ):
            if fetched is None:  # the provider is failing: fall back on what the cache still has
                for place in batch:
                    if place in old:
                        series[place] = old[place]
                        stale = True
                continue
            for place, value in zip(batch, fetched, strict=True):
                series[place] = value
                self._cache.put(keys[place], value, max_stale_age_s=MAX_STALE_AGE_S)

        return WeatherResult(
            series={place: series.get(place) for place in places},
            source=NAME,
            stale=stale,
            missing=sum(1 for place in places if series.get(place) is None),
        )

    def _fetch_batches(
        self, batches: Sequence[Sequence[LatLon]], first_day: date, last_day: date
    ) -> list[list[HourlySeries] | None]:
        """Fetch the batches, a few at a time. ``None`` marks a batch lost to an outage.

        Other failures (a response that breaks the agreed units or shape, a rejected request)
        are not outages and are raised.
        """
        deadline = current_deadline()  # worker threads do not inherit the caller's context
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_BATCHES) as pool:
            futures = [
                pool.submit(self._fetch_batch, batch, first_day, last_day, deadline)
                for batch in batches
            ]
            results: list[list[HourlySeries] | None] = []
            for future in futures:
                try:
                    results.append(future.result())
                except (UpstreamUnavailable, UpstreamTimeout):
                    results.append(None)
            return results

    def _fetch_batch(
        self,
        batch: Sequence[LatLon],
        first_day: date,
        last_day: date,
        deadline: Deadline | None,
    ) -> list[HourlySeries]:
        params = {
            "latitude": ",".join(f"{place.lat:.1f}" for place in batch),
            "longitude": ",".join(f"{place.lon:.1f}" for place in batch),
            "hourly": ",".join(HOURLY_VARIABLES),
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timeformat": "unixtime",
            "timezone": "GMT",
            "start_date": first_day.isoformat(),
            "end_date": last_day.isoformat(),
        }
        payload = self._client.get_json(
            NAME, f"{self._base_url}/v1/forecast", params=params, deadline=deadline
        )
        # One place comes back as a single object, several as an array in request order.
        locations = payload if isinstance(payload, list) else [payload]
        if len(locations) != len(batch):
            raise _shape.error(f"expected {len(batch)} locations, got {len(locations)}")
        return [_series(location) for location in locations]


def _series(location: object) -> HourlySeries:
    entry = _shape.mapping(location, "location")
    _check_units(_shape.mapping(entry.get("hourly_units"), "hourly_units"))
    hourly = _shape.mapping(entry.get("hourly"), "hourly")

    times = [_shape.integer(item, "time") for item in _shape.sequence(hourly.get("time"), "time")]
    if not times:
        raise _shape.error("no hourly times")
    if times[0] % SECONDS_PER_HOUR != 0:
        raise _shape.error("hourly times do not start on the hour")
    if any(
        later - earlier != SECONDS_PER_HOUR
        for earlier, later in zip(times, times[1:], strict=False)
    ):
        raise _shape.error("hourly times are not one hour apart")

    def column(name: str) -> tuple[float | None, ...]:
        values = _shape.sequence(hourly.get(name), name)
        if len(values) != len(times):
            raise _shape.error(f"{name} does not have one value per hour")
        return tuple(_shape.optional_number(value, name) for value in values)

    codes = _shape.sequence(hourly.get("weather_code"), "weather_code")
    if len(codes) != len(times):
        raise _shape.error("weather_code does not have one value per hour")
    return HourlySeries(
        start=datetime.fromtimestamp(times[0], tz=UTC),
        wind_mph=column("wind_speed_10m"),
        gust_mph=column("wind_gusts_10m"),
        rain_in=column("rain"),
        showers_in=column("showers"),
        snowfall_in=column("snowfall"),
        weather_code=tuple(_shape.optional_integer(value, "weather_code") for value in codes),
    )


def _check_units(units: Mapping[str, Any]) -> None:
    """Refuse a response in other units; converting silently would hide a misconfiguration."""
    for name, expected in EXPECTED_UNITS.items():
        reported = units.get(name)
        if reported != expected:
            raise _shape.error(f"{name} is reported in {reported!r}, expected {expected!r}")
