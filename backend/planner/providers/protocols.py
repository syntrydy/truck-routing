"""What the application expects from a routing provider, independent of the provider."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
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


MIN_QUERY_LENGTH = 3
MAX_QUERY_LENGTH = 100
MAX_RESULTS = 8


class PlaceKind(StrEnum):
    """What a geocoded place is, in terms the UI can show an icon for."""

    CITY = "city"
    REGION = "region"
    COUNTRY = "country"
    STREET = "street"
    ADDRESS = "address"
    PLACE = "place"


@dataclass(frozen=True, slots=True)
class Place:
    """A place a user can pick as origin or destination."""

    label: str
    lat: float
    lon: float
    kind: PlaceKind

    def __post_init__(self) -> None:
        LatLon(self.lat, self.lon)  # raises ValueError for coordinates out of range
        if not self.label:
            msg = "a place needs a label"
            raise ValueError(msg)


QUERY_LENGTH_MESSAGE = f"query must be {MIN_QUERY_LENGTH} to {MAX_QUERY_LENGTH} characters"


def normalize_query(query: str) -> str:
    """The query with whitespace collapsed, checked to be 3 to 100 characters long."""
    cleaned = " ".join(query.split())
    if not MIN_QUERY_LENGTH <= len(cleaned) <= MAX_QUERY_LENGTH:
        raise ValueError(QUERY_LENGTH_MESSAGE)
    return cleaned


class GeocodeProvider(Protocol):
    """A source of places matching a text query."""

    name: str

    def search(self, query: str) -> tuple[Place, ...]:
        """Up to ``MAX_RESULTS`` places for ``query``; no match is an empty tuple.

        Raises ``ValueError`` for a query that is too short or too long.
        """
        ...
