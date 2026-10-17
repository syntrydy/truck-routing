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
