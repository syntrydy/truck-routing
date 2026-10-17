"""Stand-in providers with controlled routes and weather for the plan service tests."""

from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime

from planner.domain.geometry import METERS_PER_MILE, cumulative_distances_m, destination_point
from planner.domain.models import HourlySeries, LatLon
from planner.infra.resilience import Deadline, current_deadline
from planner.providers.protocols import (
    ProviderRoute,
    RoutingResult,
    WeatherResult,
    rounded_point,
)

START = LatLon(40.0, -105.0)
SECONDS_PER_HOUR = 3_600


def route(
    length_mi: float,
    mph: float,
    *,
    origin: LatLon = START,
    bearing: float = 90.0,
    delay_share: float = 0.03,
) -> ProviderRoute:
    """A straight route of ``length_mi`` driven at ``mph``, with a vertex every 5 km.

    Segment times add up to ``1 / (1 + delay_share)`` of the route's own duration, like OSRM,
    whose annotations leave out turn and signal delays.
    """
    length_m = length_mi * METERS_PER_MILE
    count = max(int(length_m // 5_000), 1)
    points = tuple(
        destination_point(origin, bearing, length_m * i / count) for i in range(count + 1)
    )
    distances = [
        b - a
        for a, b in zip(
            cumulative_distances_m(points), cumulative_distances_m(points)[1:], strict=False
        )
    ]
    seconds_per_meter = SECONDS_PER_HOUR / (mph * METERS_PER_MILE)
    segment_times = tuple(distance * seconds_per_meter for distance in distances)
    return ProviderRoute(
        points=points,
        distance_m=sum(distances),
        duration_s=sum(segment_times) * (1 + delay_share),
        segment_durations_s=segment_times,
        segment_distances_m=tuple(distances),
    )


class StubRouting:
    """A routing provider that answers from a script and records what it was asked."""

    name = "stub-routing"

    def __init__(
        self,
        routes: Sequence[ProviderRoute],
        *,
        via: Callable[[LatLon], Sequence[ProviderRoute] | Exception] | None = None,
        snap_distance_m: float = 20.0,
        outcome: Exception | None = None,
        source: str = "osrm",
    ) -> None:
        self.routes_given = tuple(routes)
        self.via = via
        self.snap_distance_m = snap_distance_m
        self.outcome = outcome
        self.source = source
        self.calls: list[tuple[str, tuple[LatLon, ...]]] = []
        self.deadlines: list[Deadline | None] = []

    def routes(self, origin: LatLon, destination: LatLon) -> RoutingResult:
        self.calls.append(("routes", (origin, destination)))
        self.deadlines.append(current_deadline())
        if self.outcome is not None:
            raise self.outcome
        return RoutingResult(self.routes_given, self.snap_distance_m, self.source)

    def route_via(self, origin: LatLon, via: LatLon, destination: LatLon) -> RoutingResult:
        self.calls.append(("route_via", (origin, via, destination)))
        self.deadlines.append(current_deadline())
        answer = self.via(via) if self.via else []
        if isinstance(answer, Exception):
            raise answer
        return RoutingResult(tuple(answer), 9_000.0, self.source)


def hourly(first_day: date, days: int, **conditions: float) -> HourlySeries:
    """Constant weather for ``days`` whole UTC days from ``first_day``.

    ``conditions`` may set ``wind``, ``gust``, ``rain`` and ``snow``.
    """
    start = datetime(first_day.year, first_day.month, first_day.day, tzinfo=UTC)
    count = days * 24
    return HourlySeries(
        start=start,
        wind_mph=(conditions.get("wind", 5.0),) * count,
        gust_mph=(conditions.get("gust", 8.0),) * count,
        rain_in=(conditions.get("rain", 0.0),) * count,
        showers_in=(0.0,) * count,
        snowfall_in=(conditions.get("snow", 0.0),) * count,
        weather_code=(0,) * count,
    )


class StubWeather:
    """A weather provider whose weather depends on the place, and that records its calls."""

    name = "stub-weather"

    def __init__(
        self,
        weather_at: Callable[[LatLon], dict[str, float] | None] = lambda place: {},
        *,
        stale: bool = False,
    ) -> None:
        self.weather_at = weather_at
        self.stale = stale
        self.calls: list[tuple[list[LatLon], date, date]] = []
        self.deadlines: list[Deadline | None] = []

    def hourly(self, points: Sequence[LatLon], first_day: date, last_day: date) -> WeatherResult:
        self.calls.append((list(points), first_day, last_day))
        self.deadlines.append(current_deadline())
        days = (last_day - first_day).days + 1
        series: dict[LatLon, HourlySeries | None] = {}
        for point in dict.fromkeys(rounded_point(p) for p in points):
            conditions = self.weather_at(point)
            series[point] = None if conditions is None else hourly(first_day, days, **conditions)
        return WeatherResult(
            series=series,
            source="stub-weather",
            stale=self.stale,
            missing=sum(1 for value in series.values() if value is None),
        )
