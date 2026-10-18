"""Choosing which candidate routes to show (SPEC section 4.1, steps 2-5).

Candidates come from the routing provider (alternatives plus detours through via
points). The fastest is always kept; others are dropped when they are an overlong
detour, a detour that doubles back, or mostly follow a route that was already kept.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from planner.domain.geometry import (
    ProximityIndex,
    bearing_deg,
    cumulative_distances_m,
    haversine_m,
    min_straightness,
    perpendicular_offset,
    point_at_distance,
    sample_along,
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
# The proximity index looks at route points this far apart; the search radius is widened
# by half of that so a point truly within NEAR_DISTANCE_M of the line is never missed.
INDEX_SPACING_M = NEAR_DISTANCE_M / 4
# A detour is dropped when, over some stretch of this much road, its ends are less than
# MIN_STRAIGHTNESS of that apart in a straight line: it goes out and comes back, or leaves the
# road and rejoins it. Provider routes never go below 0.64 on the trips tried (mountain roads
# included); detours through a via point beside no good road often fall to 0.3 to 0.55.
STRAIGHTNESS_WINDOW_M = 100_000.0
MIN_STRAIGHTNESS = 0.6


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
    indexes = [_index(fastest.points)]
    for candidate in by_duration[1:]:
        if len(kept) == MAX_ROUTES:
            break
        if candidate.is_detour and candidate.distance_m > fastest.distance_m * MAX_DETOUR_RATIO:
            continue
        if candidate.is_detour and _backtracks(candidate.points):
            continue
        if _overlap_share(candidate.points, indexes) > DUPLICATE_OVERLAP_SHARE:
            continue
        kept.append(candidate)
        indexes.append(_index(candidate.points))

    notes = (_too_few_note(len(kept)),) if len(kept) < MAX_ROUTES else ()
    return Selection(routes=tuple(kept), notes=notes)


def _backtracks(points: Sequence[LatLon]) -> bool:
    """Whether the route doubles back: over some stretch it hardly gets anywhere."""
    return min_straightness(points, STRAIGHTNESS_WINDOW_M) < MIN_STRAIGHTNESS


def _too_few_note(count: int) -> str:
    if count == 1:
        return "Only 1 distinct route exists for this trip"
    return f"Only {count} distinct routes exist for this trip"


def _index(points: Sequence[LatLon]) -> ProximityIndex:
    return ProximityIndex([points], NEAR_DISTANCE_M + INDEX_SPACING_M / 2, INDEX_SPACING_M)


def _overlap_share(points: Sequence[LatLon], kept: Sequence[ProximityIndex]) -> float:
    """Share of the route's 1 km samples that lie near any kept route."""
    samples = sample_along(points, SAMPLE_SPACING_M)
    near = sum(1 for sample in samples if any(index.is_near(sample) for index in kept))
    return near / len(samples)
