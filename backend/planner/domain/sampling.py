"""Checkpoint sampling along a route with truck-speed ETAs (SPEC sections 4.2, 4.3).

Distances along the route are cumulative haversine distances of the geometry. The
driving time of each segment comes from the routing provider, floored at what a truck
limited to ``max_speed_mph`` would need.
"""

from collections.abc import Sequence

from planner.domain.geometry import METERS_PER_MILE, haversine_m
from planner.domain.models import LatLon

SECONDS_PER_HOUR = 3_600.0


def truck_durations_s(
    points: Sequence[LatLon], provider_durations_s: Sequence[float], max_speed_mph: float
) -> list[float]:
    """Per-segment driving time for a truck: ``max(provider time, distance / max speed)``.

    ``provider_durations_s`` has one entry per segment, i.e. ``len(points) - 1``.
    """
    if max_speed_mph <= 0:
        msg = "max speed must be positive"
        raise ValueError(msg)
    _check_durations(points, provider_durations_s)
    max_speed_mps = max_speed_mph * METERS_PER_MILE / SECONDS_PER_HOUR
    return [
        max(duration, haversine_m(start, end) / max_speed_mps)
        for duration, (start, end) in zip(
            provider_durations_s, zip(points, points[1:], strict=False), strict=True
        )
    ]


def _check_durations(points: Sequence[LatLon], durations_s: Sequence[float]) -> None:
    if len(points) < 2:  # noqa: PLR2004 - a route needs an origin and a destination
        msg = "route needs at least two points"
        raise ValueError(msg)
    if len(durations_s) != len(points) - 1:
        msg = "expected one duration per segment"
        raise ValueError(msg)
    if any(duration < 0 for duration in durations_s):
        msg = "segment durations must not be negative"
        raise ValueError(msg)
