"""Choosing which candidate routes to show (SPEC section 4.1, steps 2-5).

Candidates come from the routing provider (alternatives plus detours through via
points). The fastest is always kept; others are dropped when they are an overlong
detour or mostly follow a route that was already kept.
"""

from collections.abc import Sequence

from planner.domain.geometry import (
    bearing_deg,
    cumulative_distances_m,
    haversine_m,
    perpendicular_offset,
    point_at_distance,
)
from planner.domain.models import LatLon

# Via points sit this far off the middle of the fastest route: the larger of a fixed
# distance and a share of the straight-line trip length.
VIA_MIN_OFFSET_M = 15_000.0
VIA_OFFSET_SHARE = 0.08


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
