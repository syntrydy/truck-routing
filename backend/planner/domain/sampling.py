"""Checkpoint sampling along a route with truck-speed ETAs (SPEC sections 4.2, 4.3).

Distances along the route are cumulative haversine distances of the geometry. The
driving time of each segment comes from the routing provider, floored at what a truck
limited to ``max_speed_mph`` would need.
"""

from bisect import bisect_right
from collections.abc import Sequence
from datetime import datetime, timedelta

from planner.domain.geometry import (
    METERS_PER_MILE,
    cumulative_distances_m,
    haversine_m,
    point_at_distance,
)
from planner.domain.models import Checkpoint, LatLon

SECONDS_PER_HOUR = 3_600.0
# A sampled position closer than this to the destination is dropped: the destination
# checkpoint already covers it and a sliver-sized stretch would add nothing.
MIN_STRETCH_M = 1.0


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


def sample_checkpoints(
    points: Sequence[LatLon],
    durations_s: Sequence[float],
    departure: datetime,
    interval_mi: float,
) -> list[Checkpoint]:
    """Sample checkpoints every ``interval_mi`` miles, always ending at the destination.

    ``durations_s`` are the per-segment truck times from ``truck_durations_s``. A checkpoint's
    ETA is ``departure`` plus the cumulative time interpolated linearly within its segment.
    """
    if interval_mi <= 0:
        msg = "interval must be positive"
        raise ValueError(msg)
    _check_durations(points, durations_s)
    cumulative_m = cumulative_distances_m(points)
    total_m = cumulative_m[-1]
    if total_m <= 0:
        msg = "route has no length"
        raise ValueError(msg)

    cumulative_s = _cumulative(durations_s)
    return [
        Checkpoint(
            index=index,
            location=point_at_distance(points, cumulative_m, position_m),
            distance_mi=position_m / METERS_PER_MILE,
            eta=departure + timedelta(seconds=_time_at(cumulative_m, cumulative_s, position_m)),
        )
        for index, position_m in enumerate(_positions_m(total_m, interval_mi * METERS_PER_MILE))
    ]


def stretch_lengths_mi(checkpoints: Sequence[Checkpoint]) -> list[float]:
    """Length in miles of the stretch each checkpoint owns, up to the next checkpoint.

    The last checkpoint (the destination) owns no stretch, so the result has one entry
    fewer than ``checkpoints``.
    """
    return [
        nxt.distance_mi - current.distance_mi
        for current, nxt in zip(checkpoints, checkpoints[1:], strict=False)
    ]


def _positions_m(total_m: float, interval_m: float) -> list[float]:
    """Distances along the route to sample: 0, d, 2d, ... and always the destination."""
    positions = [0.0]
    step = 1
    while step * interval_m < total_m - MIN_STRETCH_M:
        positions.append(step * interval_m)
        step += 1
    positions.append(total_m)
    return positions


def _cumulative(values: Sequence[float]) -> list[float]:
    total = 0.0
    cumulative = [0.0]
    for value in values:
        total += value
        cumulative.append(total)
    return cumulative


def _time_at(
    cumulative_m: Sequence[float], cumulative_s: Sequence[float], position_m: float
) -> float:
    """Elapsed seconds at ``position_m``, interpolating linearly within a segment."""
    if position_m >= cumulative_m[-1]:
        return cumulative_s[-1]
    end = bisect_right(cumulative_m, position_m)
    start = end - 1
    fraction = (position_m - cumulative_m[start]) / (cumulative_m[end] - cumulative_m[start])
    return cumulative_s[start] + fraction * (cumulative_s[end] - cumulative_s[start])


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
