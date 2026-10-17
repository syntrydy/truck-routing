"""Pure geometry on WGS84 coordinates. Distances are in meters, angles in degrees.

Great-circle maths (haversine, bearing, destination) use a spherical Earth. Distances
to segments and polylines use a local equirectangular projection around the reference
point, which is accurate to well under 1% over the tens of kilometers that matter here.
"""

import math
from bisect import bisect_right
from collections.abc import Sequence

from planner.domain.models import LatLon

EARTH_RADIUS_M = 6_371_008.8
METERS_PER_MILE = 1_609.344
METERS_PER_DEGREE = EARTH_RADIUS_M * math.pi / 180.0

type Point2D = tuple[float, float]


def haversine_m(a: LatLon, b: LatLon) -> float:
    """Great-circle distance between two coordinates."""
    lat_a, lat_b = math.radians(a.lat), math.radians(b.lat)
    d_lat = lat_b - lat_a
    d_lon = math.radians(b.lon - a.lon)
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def cumulative_distances_m(points: Sequence[LatLon]) -> list[float]:
    """Distance from the first point to each point along the polyline (starts at 0)."""
    cumulative: list[float] = []
    total = 0.0
    for index, point in enumerate(points):
        if index > 0:
            total += haversine_m(points[index - 1], point)
        cumulative.append(total)
    return cumulative


def point_at_distance(
    points: Sequence[LatLon], cumulative_m: Sequence[float], distance_m: float
) -> LatLon:
    """Interpolate the point ``distance_m`` along the polyline.

    ``cumulative_m`` comes from ``cumulative_distances_m(points)``. Distances outside
    the polyline are clamped to its first and last point.
    """
    if not points:
        msg = "polyline has no points"
        raise ValueError(msg)
    if len(points) != len(cumulative_m):
        msg = "points and cumulative distances differ in length"
        raise ValueError(msg)
    if distance_m <= 0 or len(points) == 1:
        return points[0]
    if distance_m >= cumulative_m[-1]:
        return points[-1]

    end = bisect_right(cumulative_m, distance_m)
    start = end - 1
    span = cumulative_m[end] - cumulative_m[start]
    fraction = (distance_m - cumulative_m[start]) / span
    a, b = points[start], points[end]
    return LatLon(a.lat + (b.lat - a.lat) * fraction, a.lon + (b.lon - a.lon) * fraction)


def bearing_deg(a: LatLon, b: LatLon) -> float:
    """Initial great-circle bearing from ``a`` to ``b``, clockwise from north in [0, 360)."""
    lat_a, lat_b = math.radians(a.lat), math.radians(b.lat)
    d_lon = math.radians(b.lon - a.lon)
    y = math.sin(d_lon) * math.cos(lat_b)
    x = math.cos(lat_a) * math.sin(lat_b) - math.sin(lat_a) * math.cos(lat_b) * math.cos(d_lon)
    return math.degrees(math.atan2(y, x)) % 360.0


def destination_point(origin: LatLon, bearing: float, distance_m: float) -> LatLon:
    """Point reached by travelling ``distance_m`` from ``origin`` on an initial ``bearing``."""
    angular = distance_m / EARTH_RADIUS_M
    theta = math.radians(bearing)
    lat1, lon1 = math.radians(origin.lat), math.radians(origin.lon)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular) + math.cos(lat1) * math.sin(angular) * math.cos(theta)
    )
    lon2 = lon1 + math.atan2(
        math.sin(theta) * math.sin(angular) * math.cos(lat1),
        math.cos(angular) - math.sin(lat1) * math.sin(lat2),
    )
    lon_deg = (math.degrees(lon2) + 540.0) % 360.0 - 180.0
    return LatLon(math.degrees(lat2), lon_deg)


def perpendicular_offset(point: LatLon, heading_deg: float, offset_m: float) -> LatLon:
    """Move ``point`` sideways from a ``heading_deg``: positive is right, negative is left."""
    side = heading_deg + 90.0 if offset_m >= 0 else heading_deg - 90.0
    return destination_point(point, side % 360.0, abs(offset_m))


def simplify(points: Sequence[LatLon], tolerance_m: float) -> list[LatLon]:
    """Douglas-Peucker simplification; the first and last points are always kept.

    Every dropped point lies within about ``tolerance_m`` of the simplified line.
    """
    if tolerance_m < 0:
        msg = "tolerance must not be negative"
        raise ValueError(msg)
    if len(points) < 3:  # noqa: PLR2004 - fewer than three points cannot be simplified
        return list(points)

    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:  # noqa: PLR2004 - no interior points
            continue
        farthest, farthest_m = _farthest_from_chord(points, first, last)
        if farthest_m > tolerance_m:
            keep[farthest] = True
            stack.append((first, farthest))
            stack.append((farthest, last))
    return [point for point, kept in zip(points, keep, strict=True) if kept]


def distance_to_polyline_m(point: LatLon, polyline: Sequence[LatLon]) -> float:
    """Shortest distance from ``point`` to any segment of ``polyline``."""
    if not polyline:
        msg = "polyline has no points"
        raise ValueError(msg)
    lat0, lon0 = point.lat, point.lon
    cos_lat0 = math.cos(math.radians(lat0))
    projected = [_project(vertex, lat0, lon0, cos_lat0) for vertex in polyline]
    if len(projected) == 1:
        return math.hypot(*projected[0])
    return min(
        _distance_to_segment((0.0, 0.0), start, end)
        for start, end in zip(projected, projected[1:], strict=False)
    )


def _farthest_from_chord(points: Sequence[LatLon], first: int, last: int) -> tuple[int, float]:
    """Index and distance of the interior point farthest from the chord ``first``-``last``."""
    lat0 = (points[first].lat + points[last].lat) / 2
    lon0 = points[first].lon
    cos_lat0 = math.cos(math.radians(lat0))
    start = _project(points[first], lat0, lon0, cos_lat0)
    end = _project(points[last], lat0, lon0, cos_lat0)
    farthest, farthest_m = first + 1, -1.0
    for index in range(first + 1, last):
        distance = _distance_to_segment(_project(points[index], lat0, lon0, cos_lat0), start, end)
        if distance > farthest_m:
            farthest, farthest_m = index, distance
    return farthest, farthest_m


def _project(point: LatLon, lat0: float, lon0: float, cos_lat0: float) -> Point2D:
    """Equirectangular projection to meters east and north of the reference point."""
    d_lon = (point.lon - lon0 + 180.0) % 360.0 - 180.0
    return d_lon * cos_lat0 * METERS_PER_DEGREE, (point.lat - lat0) * METERS_PER_DEGREE


def _distance_to_segment(p: Point2D, a: Point2D, b: Point2D) -> float:
    """Distance from ``p`` to the segment ``a``-``b`` in the plane."""
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0.0:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length_sq))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))
