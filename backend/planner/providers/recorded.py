"""A recorded corridor and storm, replayed for the demo (``fixtures/demo``, see its README).

Routing returns the three recorded roads between Denver and Salt Lake City. Weather replays the
historical forecast of the January 2024 wind storm on I-80 in Wyoming, moved in time so that its
worst hours begin at the departure hour, whenever the demo is asked for. A place takes the
weather of the nearest recorded place. Nothing here touches the network.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from planner.domain.geometry import haversine_m
from planner.domain.models import HourlySeries, LatLon
from planner.providers.protocols import (
    NoRoute,
    ProviderRoute,
    RoutingResult,
    WeatherResult,
    rounded_point,
)
from planner.providers.weather_openmeteo import parse_location

SOURCE = "demo"
DEMO_ORIGIN = LatLon(39.7392, -104.9903)
DEMO_DESTINATION = LatLon(40.7608, -111.8910)
# Hour 56 of the recording is 2024-01-17 08:00 UTC: a truck leaving Denver then meets the
# worst wind (about 50 mph sustained) near Laramie about three hours later.
STORM_START_HOUR = 56
SECONDS_PER_HOUR = 3_600
HOURS_PER_DAY = 24
ROUTES_FILE = "denver_salt_lake_routes.json"
WEATHER_FILE = "denver_salt_lake_weather.json"


@dataclass(frozen=True, slots=True)
class RecordedPlace:
    """The recorded hourly weather at one place."""

    location: LatLon
    series: HourlySeries


@dataclass(frozen=True, slots=True)
class DemoScenario:
    """The recorded roads and weather of the demo."""

    routes: tuple[ProviderRoute, ...]
    places: tuple[RecordedPlace, ...]


def load_scenario(directory: Path) -> DemoScenario:
    """Read the recordings in ``directory``."""
    routes = json.loads((directory / ROUTES_FILE).read_text())["routes"]
    weather = json.loads((directory / WEATHER_FILE).read_text())["places"]
    return DemoScenario(
        routes=tuple(_route(recorded) for recorded in routes),
        places=tuple(_place(recorded) for recorded in weather),
    )


def _route(recorded: dict[str, Any]) -> ProviderRoute:
    """A route whose segment times share the recorded total in proportion to their lengths."""
    points = tuple(LatLon(lat, lon) for lon, lat in recorded["points"])
    distances = tuple(haversine_m(a, b) for a, b in zip(points, points[1:], strict=False))
    duration_s = float(recorded["duration_s"])
    return ProviderRoute(
        points=points,
        distance_m=float(recorded["distance_m"]),
        duration_s=duration_s,
        segment_durations_s=tuple(duration_s * gap / sum(distances) for gap in distances),
        segment_distances_m=distances,
    )


def _place(recorded: dict[str, Any]) -> RecordedPlace:
    location = {"hourly_units": recorded["units"], "hourly": recorded["hourly"]}
    return RecordedPlace(LatLon(recorded["lat"], recorded["lon"]), parse_location(location))


class RecordedRouting:
    """The recorded roads, whatever the places asked for."""

    name = SOURCE

    def __init__(self, scenario: DemoScenario) -> None:
        self._routes = tuple(sorted(scenario.routes, key=lambda route: route.duration_s))

    def routes(self, origin: LatLon, destination: LatLon) -> RoutingResult:  # noqa: ARG002
        return RoutingResult(routes=self._routes, snap_distance_m=0.0, source=SOURCE)

    def route_via(self, origin: LatLon, via: LatLon, destination: LatLon) -> RoutingResult:
        """There is nothing recorded for detours; the three roads are all there is."""
        msg = "the demo has only its recorded roads"
        raise NoRoute(msg)


class RecordedWeather:
    """The recorded storm, replayed to start at ``departure_hour``."""

    name = SOURCE

    def __init__(self, scenario: DemoScenario, departure_hour: datetime) -> None:
        self._places = scenario.places
        self._departure_hour = departure_hour

    def hourly(self, points: Sequence[LatLon], first_day: date, last_day: date) -> WeatherResult:
        start = datetime(first_day.year, first_day.month, first_day.day, tzinfo=UTC)
        hours = ((last_day - first_day).days + 1) * HOURS_PER_DAY
        replayed: dict[int, HourlySeries] = {}
        series: dict[LatLon, HourlySeries | None] = {}
        for point in points:
            place = rounded_point(point)
            index = self._nearest(place)
            if index not in replayed:
                replayed[index] = self._replay(self._places[index].series, start, hours)
            series[place] = replayed[index]
        return WeatherResult(series=series, source=SOURCE, stale=False, missing=0)

    def _nearest(self, place: LatLon) -> int:
        distances = [haversine_m(place, recorded.location) for recorded in self._places]
        return distances.index(min(distances))

    def _replay(self, recorded: HourlySeries, start: datetime, hours: int) -> HourlySeries:
        """``hours`` hours from ``start``, where the departure hour is the storm's start."""
        shift = STORM_START_HOUR + int(
            (start - self._departure_hour) / timedelta(seconds=SECONDS_PER_HOUR)
        )

        def column[T](values: tuple[T | None, ...]) -> tuple[T | None, ...]:
            return tuple(
                values[shift + hour] if 0 <= shift + hour < len(values) else None
                for hour in range(hours)
            )

        return HourlySeries(
            start=start,
            wind_mph=column(recorded.wind_mph),
            gust_mph=column(recorded.gust_mph),
            rain_in=column(recorded.rain_in),
            showers_in=column(recorded.showers_in),
            snowfall_in=column(recorded.snowfall_in),
            weather_code=column(recorded.weather_code),
        )
