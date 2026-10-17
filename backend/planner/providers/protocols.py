"""What the application expects from a routing provider, independent of the provider."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from planner.domain.models import HourlySeries, LatLon

WEATHER_GRID_DECIMALS = 1


class NoRoute(Exception):  # noqa: N818 - named for the API error code it maps to
    """The provider found no drivable route between the points (HTTP 422 NO_ROUTE)."""


@dataclass(frozen=True, slots=True)
class ProviderRoute:
    """One route as the provider describes it.

    ``segment_durations_s[i]`` and ``segment_distances_m[i]`` belong to the stretch between
    ``points[i]`` and ``points[i + 1]``, so both have ``len(points) - 1`` entries.
    """

    points: tuple[LatLon, ...]
    distance_m: float
    duration_s: float
    segment_durations_s: tuple[float, ...]
    segment_distances_m: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class RoutingResult:
    """Routes from one provider call, best first.

    ``snap_distance_m`` is the largest distance between a requested point and the road
    the provider moved it to; a large value means a point is far from any road.
    """

    routes: tuple[ProviderRoute, ...]
    snap_distance_m: float
    source: str


class RoutingProvider(Protocol):
    """A source of driving routes."""

    name: str

    def routes(self, origin: LatLon, destination: LatLon) -> RoutingResult:
        """The best route and the provider's alternatives, fastest first.

        Raises ``NoRoute`` when there is no drivable connection.
        """
        ...

    def route_via(self, origin: LatLon, via: LatLon, destination: LatLon) -> RoutingResult:
        """A single route from ``origin`` to ``destination`` passing through ``via``."""
        ...


def rounded_point(point: LatLon) -> LatLon:
    """The weather grid place for ``point``: weather is looked up per 0.1 degrees."""
    return LatLon(round(point.lat, WEATHER_GRID_DECIMALS), round(point.lon, WEATHER_GRID_DECIMALS))


@dataclass(frozen=True, slots=True)
class WeatherResult:
    """Hourly weather for a set of places, keyed by the place rounded to 0.1 degrees.

    A place maps to ``None`` when no weather could be had for it, so the caller reports it
    as unknown. ``stale`` is true when any series came from the cache after it had stopped
    being fresh because the provider failed. ``missing`` counts the places without weather.
    """

    series: Mapping[LatLon, HourlySeries | None]
    source: str
    stale: bool = False
    missing: int = 0


class WeatherProvider(Protocol):
    """A source of hourly weather."""

    name: str

    def hourly(self, points: Sequence[LatLon], first_day: date, last_day: date) -> WeatherResult:
        """Hourly weather for the UTC days ``first_day`` to ``last_day`` at each place.

        An outage degrades to missing places rather than raising; a response that breaks the
        agreed units or shape raises ``UpstreamContractError``.
        """
        ...
