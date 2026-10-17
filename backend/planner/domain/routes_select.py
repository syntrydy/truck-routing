"""Choosing which candidate routes to show (SPEC section 4.1, steps 2-5).

Candidates come from the routing provider (alternatives plus detours through via
points). The fastest is always kept; others are dropped when they are an overlong
detour or mostly follow a route that was already kept.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from planner.domain.geometry import (
    METERS_PER_DEGREE,
    bearing_deg,
    cumulative_distances_m,
    haversine_m,
    perpendicular_offset,
    point_at_distance,
)
from planner.domain.models import LatLon

MAX_ROUTES = 3
# A detour may be at most this much longer than the fastest route.
MAX_DETOUR_RATIO = 1.40
# Via points sit this far off the middle of the fastest route: the larger of a fixed
# distance and a share of the straight-line trip length.
VIA_MIN_OFFSET_M = 15_000.0
VIA_OFFSET_SHARE = 0.08
# A candidate is a duplicate when more than this share of its samples is near a kept route.
DUPLICATE_OVERLAP_SHARE = 0.85
SAMPLE_SPACING_M = 1_000.0
NEAR_DISTANCE_M = 1_000.0
# The proximity index looks at route points this far apart; it widens the near-distance by
# half of that so a point truly within NEAR_DISTANCE_M of the line is never missed.
INDEX_SPACING_M = NEAR_DISTANCE_M / 4
MAX_INDEX_LATITUDE = 89.0
LATITUDE_MARGIN_DEG = 0.1


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    """A route offered by the routing provider.

    ``is_detour`` marks routes made by forcing a via point; only those are subject to
    the length limit, since provider alternatives are already sensible.
    """

    route_id: str
    points: Sequence[LatLon]
    distance_m: float
    duration_s: float
    is_detour: bool = False

    def __post_init__(self) -> None:
        if len(self.points) < 2:  # noqa: PLR2004 - a route has an origin and a destination
            msg = "a route needs at least two points"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Selection:
    """The routes to show, fastest first, and notes for the user."""

    routes: tuple[RouteCandidate, ...]
    notes: tuple[str, ...]


def via_points(
    origin: LatLon, destination: LatLon, fastest_route: Sequence[LatLon]
) -> tuple[LatLon, LatLon]:
    """Two via points, one on each side of the middle of the fastest route."""
    cumulative = cumulative_distances_m(fastest_route)
    middle = point_at_distance(fastest_route, cumulative, cumulative[-1] / 2)
    offset_m = max(VIA_MIN_OFFSET_M, VIA_OFFSET_SHARE * haversine_m(origin, destination))
    heading = bearing_deg(origin, destination)
    return (
        perpendicular_offset(middle, heading, offset_m),
        perpendicular_offset(middle, heading, -offset_m),
    )


def select_routes(candidates: Sequence[RouteCandidate]) -> Selection:
    """Pick up to ``MAX_ROUTES`` distinct routes, ordered by duration."""
    if not candidates:
        msg = "no candidate routes"
        raise ValueError(msg)

    by_duration = sorted(candidates, key=lambda route: route.duration_s)
    fastest = by_duration[0]
    kept = [fastest]
    indexes = [_ProximityIndex(fastest.points)]
    for candidate in by_duration[1:]:
        if len(kept) == MAX_ROUTES:
            break
        if candidate.is_detour and candidate.distance_m > fastest.distance_m * MAX_DETOUR_RATIO:
            continue
        if _overlap_share(candidate.points, indexes) > DUPLICATE_OVERLAP_SHARE:
            continue
        kept.append(candidate)
        indexes.append(_ProximityIndex(candidate.points))

    notes = (_too_few_note(len(kept)),) if len(kept) < MAX_ROUTES else ()
    return Selection(routes=tuple(kept), notes=notes)


def _too_few_note(count: int) -> str:
    if count == 1:
        return "Only 1 distinct route exists for this trip"
    return f"Only {count} distinct routes exist for this trip"


def _overlap_share(points: Sequence[LatLon], kept: Sequence["_ProximityIndex"]) -> float:
    """Share of the route's 1 km samples that lie near any kept route."""
    samples = _sample_every(points, SAMPLE_SPACING_M)
    near = sum(1 for sample in samples if any(index.is_near(sample) for index in kept))
    return near / len(samples)


def _sample_every(points: Sequence[LatLon], spacing_m: float) -> list[LatLon]:
    """Points every ``spacing_m`` along the route, always including the last point."""
    cumulative = cumulative_distances_m(points)
    total = cumulative[-1]
    steps = math.floor(total / spacing_m)
    samples = [point_at_distance(points, cumulative, step * spacing_m) for step in range(steps + 1)]
    if steps * spacing_m < total:
        samples.append(points[-1])
    return samples


class _ProximityIndex:
    """Answers "is this point within ``NEAR_DISTANCE_M`` of the route?" in near-constant time.

    The route is densified every ``INDEX_SPACING_M`` and its points are bucketed in a grid
    whose cells are at least as large as the search radius, so only the 3x3 cells around a
    query need checking. Distances are measured to the densified points, which can
    overstate the true distance by at most half the spacing, hence the widened radius.
    """

    def __init__(self, route: Sequence[LatLon]) -> None:
        self._reach_m = NEAR_DISTANCE_M + INDEX_SPACING_M / 2
        dense = _sample_every(route, INDEX_SPACING_M)
        max_latitude = min(
            max(abs(point.lat) for point in dense) + LATITUDE_MARGIN_DEG, MAX_INDEX_LATITUDE
        )
        self._cell_lat = self._reach_m / METERS_PER_DEGREE
        self._cell_lon = self._cell_lat / math.cos(math.radians(max_latitude))
        self._cells: dict[tuple[int, int], list[LatLon]] = {}
        for point in dense:
            self._cells.setdefault(self._cell_of(point), []).append(point)

    def is_near(self, point: LatLon) -> bool:
        row, col = self._cell_of(point)
        return any(
            haversine_m(point, candidate) <= self._reach_m
            for d_row in (-1, 0, 1)
            for d_col in (-1, 0, 1)
            for candidate in self._cells.get((row + d_row, col + d_col), ())
        )

    def _cell_of(self, point: LatLon) -> tuple[int, int]:
        return math.floor(point.lat / self._cell_lat), math.floor(point.lon / self._cell_lon)
