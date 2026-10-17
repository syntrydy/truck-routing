"""openrouteservice routing adapter, the fallback when OSRM is down (SPEC sections 2, 4.1).

Uses the ``driving-hgv`` (heavy goods vehicle) profile. Alternatives are only offered for
short trips, so this adapter returns a single route, plain or through a waypoint.

ORS reports driving time per step rather than per geometry segment, so each step's time
and distance are spread over its segments in proportion to their length.

Details taken from the ORS documentation are the endpoint, the GeoJSON structure and the
error codes 2009 and 2010. The API key header, the request body and the shape of error
bodies are not stated there and follow ORS's public examples; ``tests/providers`` has an
opt-in live test (``-m live`` with ``ORS_API_KEY`` set) to confirm them against the service.
"""

import json
from collections.abc import Sequence
from typing import Any

from planner.domain.geometry import haversine_m
from planner.domain.models import LatLon
from planner.infra.errors import UpstreamError
from planner.infra.http import UpstreamClient
from planner.providers.jsonshape import JsonShape
from planner.providers.protocols import NoRoute, ProviderRoute, RoutingResult

NAME = "openrouteservice"
DEFAULT_BASE_URL = "https://api.openrouteservice.org"
PROFILE = "driving-hgv"
# 2009: route could not be found between locations. 2010: point was not found.
NO_ROUTE_CODES = frozenset({2009, 2010})
MIN_ROUTE_POINTS = 2

_shape = JsonShape(NAME)


class OrsRoutingProvider:
    """Routes from openrouteservice through the resilient upstream client."""

    name = NAME

    def __init__(
        self, client: UpstreamClient, api_key: str, base_url: str = DEFAULT_BASE_URL
    ) -> None:
        if not api_key:
            msg = "an openrouteservice API key is required"
            raise ValueError(msg)
        self._client = client
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def __repr__(self) -> str:
        return f"{type(self).__name__}(base_url={self._base_url!r})"  # never shows the key

    def routes(self, origin: LatLon, destination: LatLon) -> RoutingResult:
        return self._fetch([origin, destination])

    def route_via(self, origin: LatLon, via: LatLon, destination: LatLon) -> RoutingResult:
        return self._fetch([origin, via, destination])

    def _fetch(self, waypoints: Sequence[LatLon]) -> RoutingResult:
        body = {
            "coordinates": [[point.lon, point.lat] for point in waypoints],
            "instructions": True,  # the steps carry the driving times
        }
        try:
            payload = self._client.post_json(
                NAME,
                f"{self._base_url}/v2/directions/{PROFILE}/geojson",
                json=body,
                headers={"Authorization": self._api_key},
            )
        except UpstreamError as error:
            message = _no_route_message(error) if type(error) is UpstreamError else None
            if message is not None:
                raise NoRoute(message) from error
            raise
        return _parse(payload, waypoints)


def _no_route_message(error: UpstreamError) -> str | None:
    """ORS reports an unroutable request as an error body with a numeric code."""
    if not error.body:
        return None
    try:
        body = json.loads(error.body)
    except ValueError:
        return None
    detail = body.get("error") if isinstance(body, dict) else None
    if not isinstance(detail, dict) or _code(detail.get("code")) not in NO_ROUTE_CODES:
        return None
    return str(detail.get("message", detail["code"]))


def _code(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _parse(payload: object, waypoints: Sequence[LatLon]) -> RoutingResult:
    root = _shape.mapping(payload, "response")
    features = _shape.sequence(root.get("features"), "features")
    if not features:
        raise _shape.error("no routes in the response")
    feature = _shape.mapping(features[0], "feature")

    geometry = _shape.mapping(feature.get("geometry"), "geometry")
    if geometry.get("type") != "LineString":
        raise _shape.error("route geometry is not a LineString")
    points = tuple(
        _shape.point(coordinate)
        for coordinate in _shape.sequence(geometry.get("coordinates"), "coordinates")
    )
    if len(points) < MIN_ROUTE_POINTS:
        raise _shape.error("route has fewer than two points")

    properties = _shape.mapping(feature.get("properties"), "properties")
    summary = _shape.mapping(properties.get("summary"), "summary")
    steps = _steps(properties, len(points))
    durations, distances = _spread(steps, points)
    snap_distance_m = _snap_distance(properties, waypoints, points)

    route = ProviderRoute(
        points=points,
        distance_m=_shape.number(summary.get("distance"), "route distance"),
        duration_s=_shape.number(summary.get("duration"), "route duration"),
        segment_durations_s=tuple(durations),
        segment_distances_m=tuple(distances),
    )
    return RoutingResult(routes=(route,), snap_distance_m=snap_distance_m, source=NAME)


def _steps(properties: Any, point_count: int) -> list[tuple[float, float, int, int]]:
    """The route steps as (distance, duration, first point, last point), checked to tile it."""
    steps: list[tuple[float, float, int, int]] = []
    for segment in _shape.sequence(properties.get("segments"), "segments"):
        for item in _shape.sequence(_shape.mapping(segment, "segment").get("steps"), "steps"):
            step = _shape.mapping(item, "step")
            first, last = _index_pair(step.get("way_points"), point_count)
            steps.append(
                (
                    _shape.number(step.get("distance"), "step distance"),
                    _shape.number(step.get("duration"), "step duration"),
                    first,
                    last,
                )
            )
    if not steps or steps[0][2] != 0 or steps[-1][3] != point_count - 1:
        raise _shape.error("route steps do not cover the geometry")
    if any(later[2] != earlier[3] for earlier, later in zip(steps, steps[1:], strict=False)):
        raise _shape.error("route steps are not contiguous")
    return steps


def _index_pair(value: object, point_count: int) -> tuple[int, int]:
    pair = _shape.sequence(value, "way_points")
    if len(pair) != MIN_ROUTE_POINTS:
        raise _shape.error("way_points does not hold two indices")
    first, last = (_index(item, point_count) for item in pair)
    if last < first:
        raise _shape.error("way_points are not in order")
    return first, last


def _index(value: object, point_count: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < point_count:
        raise _shape.error("way_point index is outside the geometry")
    return value


def _spread(
    steps: Sequence[tuple[float, float, int, int]], points: Sequence[LatLon]
) -> tuple[list[float], list[float]]:
    """Per-segment durations and distances from per-step totals, in proportion to length."""
    durations = [0.0] * (len(points) - 1)
    distances = [0.0] * (len(points) - 1)
    for distance, duration, first, last in steps:
        if first == last:
            if distance or duration:
                raise _shape.error("a step without length has a distance or duration")
            continue
        lengths = [haversine_m(points[i], points[i + 1]) for i in range(first, last)]
        total = sum(lengths)
        for offset, length in enumerate(lengths):
            share = length / total if total > 0 else 1 / len(lengths)
            durations[first + offset] += duration * share
            distances[first + offset] += distance * share
    return durations, distances


def _snap_distance(properties: Any, waypoints: Sequence[LatLon], points: Sequence[LatLon]) -> float:
    """Largest distance between a requested point and where the route reaches the road."""
    indices = [
        _index(item, len(points))
        for item in _shape.sequence(properties.get("way_points"), "way_points")
    ]
    if len(indices) != len(waypoints):
        raise _shape.error("way_points do not match the requested points")
    if any(later < earlier for earlier, later in zip(indices, indices[1:], strict=False)):
        raise _shape.error("way_points are not in order")
    return max(haversine_m(wanted, points[i]) for wanted, i in zip(waypoints, indices, strict=True))
