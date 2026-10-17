"""OSRM routing adapter (SPEC section 4.1).

Coordinates travel as ``lon,lat`` in the URL path. The response is validated strictly: a
body that is not what the adapter relies on is an ``UpstreamContractError``, never a guess.
"""

import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

from planner.domain.models import LatLon
from planner.infra.errors import UpstreamContractError, UpstreamError
from planner.infra.http import UpstreamClient
from planner.providers.protocols import NoRoute, ProviderRoute, RoutingResult

NAME = "osrm"
DEFAULT_BASE_URL = "https://router.project-osrm.org"
MAX_ALTERNATIVES = 3
# OSRM codes that mean "no drivable connection" rather than a malformed request.
NO_ROUTE_CODES = frozenset({"NoRoute", "NoSegment"})
OK_CODE = "Ok"
POINT_SIZE = 2  # [lon, lat]; some servers append an altitude, which is ignored
MIN_ROUTE_POINTS = 2


class OsrmRoutingProvider:
    """Routes from an OSRM server through the resilient upstream client."""

    name = NAME

    def __init__(self, client: UpstreamClient, base_url: str = DEFAULT_BASE_URL) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    def routes(self, origin: LatLon, destination: LatLon) -> RoutingResult:
        return self._fetch([origin, destination], alternatives=str(MAX_ALTERNATIVES))

    def route_via(self, origin: LatLon, via: LatLon, destination: LatLon) -> RoutingResult:
        return self._fetch([origin, via, destination], alternatives="false")

    def _fetch(self, waypoints: Sequence[LatLon], *, alternatives: str) -> RoutingResult:
        path = ";".join(f"{point.lon:.6f},{point.lat:.6f}" for point in waypoints)
        params = {
            "alternatives": alternatives,
            "overview": "full",
            "geometries": "geojson",
            "annotations": "distance,duration",
            "steps": "false",
        }
        try:
            payload = self._client.get_json(
                NAME, f"{self._base_url}/route/v1/driving/{path}", params=params
            )
        except UpstreamError as error:
            message = _no_route_message(error) if type(error) is UpstreamError else None
            if message is not None:
                raise NoRoute(message) from error
            raise
        return _parse(payload)


def _no_route_message(error: UpstreamError) -> str | None:
    """OSRM reports "no route" as HTTP 400 with a JSON body naming the code; return its message."""
    if error.status != 400 or not error.body:  # noqa: PLR2004 - HTTP Bad Request
        return None
    try:
        body = json.loads(error.body)
    except ValueError:
        return None
    if not isinstance(body, dict) or body.get("code") not in NO_ROUTE_CODES:
        return None
    return str(body.get("message", body["code"]))


def _parse(payload: object) -> RoutingResult:
    root = _mapping(payload, "response")
    code = root.get("code")
    if code in NO_ROUTE_CODES:
        raise NoRoute(str(root.get("message", code)))
    if code != OK_CODE:
        raise _contract(f"unexpected response code {code!r}")

    routes = tuple(_route(item) for item in _sequence(root.get("routes"), "routes"))
    if not routes:
        raise _contract("no routes in an Ok response")
    snaps = [
        _number(_mapping(item, "waypoint").get("distance"), "waypoint distance")
        for item in _sequence(root.get("waypoints"), "waypoints")
    ]
    if not snaps:
        raise _contract("no waypoints in the response")
    return RoutingResult(routes=routes, snap_distance_m=max(snaps), source=NAME)


def _route(item: object) -> ProviderRoute:
    route = _mapping(item, "route")
    geometry = _mapping(route.get("geometry"), "geometry")
    if geometry.get("type") != "LineString":
        raise _contract("route geometry is not a LineString")
    points = tuple(
        _point(coordinate) for coordinate in _sequence(geometry.get("coordinates"), "coordinates")
    )
    if len(points) < MIN_ROUTE_POINTS:
        raise _contract("route has fewer than two points")

    durations: list[float] = []
    distances: list[float] = []
    for leg in _sequence(route.get("legs"), "legs"):
        annotation = _mapping(_mapping(leg, "leg").get("annotation"), "annotation")
        durations.extend(_numbers(annotation.get("duration"), "annotation duration"))
        distances.extend(_numbers(annotation.get("distance"), "annotation distance"))
    if len(durations) != len(points) - 1 or len(distances) != len(points) - 1:
        raise _contract("segment annotations do not match the route geometry")

    return ProviderRoute(
        points=points,
        distance_m=_number(route.get("distance"), "route distance"),
        duration_s=_number(route.get("duration"), "route duration"),
        segment_durations_s=tuple(durations),
        segment_distances_m=tuple(distances),
    )


def _point(coordinate: object) -> LatLon:
    values = _sequence(coordinate, "coordinate")
    if len(values) < POINT_SIZE:
        raise _contract("coordinate has fewer than two values")
    lon, lat = _number(values[0], "longitude"), _number(values[1], "latitude")
    try:
        return LatLon(lat, lon)
    except ValueError as error:
        raise _contract(f"coordinate out of range: {error}") from error


def _mapping(value: object, what: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise _contract(f"{what} is not an object")
    return value


def _sequence(value: object, what: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise _contract(f"{what} is not a list")
    return value


def _numbers(value: object, what: str) -> list[float]:
    return [_number(item, what) for item in _sequence(value, what)]


def _number(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise _contract(f"{what} is not a finite number")
    if value < 0 and what not in {"longitude", "latitude"}:
        raise _contract(f"{what} is negative")
    return float(value)


def _contract(message: str) -> UpstreamContractError:
    return UpstreamContractError(NAME, message)
