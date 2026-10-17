import pytest

from planner.domain.geometry import destination_point, haversine_m
from planner.domain.models import LatLon
from planner.domain.routes_select import via_points

START = LatLon(40.0, -100.0)
EAST = 90.0
NORTH = 0.0
KM = 1_000.0


def line(origin: LatLon, bearing: float, length_m: float, step_m: float = 5 * KM) -> list[LatLon]:
    """A straight route from ``origin`` with a vertex every ``step_m``."""
    count = int(length_m // step_m)
    points = [destination_point(origin, bearing, step * step_m) for step in range(count + 1)]
    if count * step_m < length_m:
        points.append(destination_point(origin, bearing, length_m))
    return points


class TestViaPoints:
    def test_points_are_on_either_side_of_the_route_middle(self) -> None:
        route = line(START, EAST, 200 * KM)
        destination = route[-1]

        right, left = via_points(START, destination, route)

        middle = destination_point(START, EAST, 100 * KM)
        assert right.lat < middle.lat < left.lat  # travelling east, right is south
        assert haversine_m(middle, right) == pytest.approx(16 * KM, rel=0.005)
        assert haversine_m(middle, left) == pytest.approx(16 * KM, rel=0.005)

    def test_short_trips_use_the_minimum_offset(self) -> None:
        route = line(START, EAST, 50 * KM)

        right, left = via_points(START, route[-1], route)

        middle = destination_point(START, EAST, 25 * KM)
        assert haversine_m(middle, right) == pytest.approx(15 * KM, rel=0.005)
        assert haversine_m(middle, left) == pytest.approx(15 * KM, rel=0.005)

    def test_offset_is_perpendicular_to_the_origin_destination_bearing(self) -> None:
        route = line(START, 45.0, 120 * KM)

        right, left = via_points(START, route[-1], route)

        middle = destination_point(START, 45.0, 60 * KM)
        assert haversine_m(right, left) == pytest.approx(2 * 15 * KM, rel=0.01)
        assert (right.lat - middle.lat) < 0 < (left.lat - middle.lat)

    def test_middle_follows_the_route_not_the_straight_line(self) -> None:
        bend = destination_point(START, EAST, 100 * KM)
        route = [START, bend, destination_point(bend, NORTH, 100 * KM)]

        right, left = via_points(START, route[-1], route)

        assert haversine_m(bend, right) == pytest.approx(15 * KM, rel=0.005)
        assert haversine_m(bend, left) == pytest.approx(15 * KM, rel=0.005)
