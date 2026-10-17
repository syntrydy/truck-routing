import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from planner.domain.geometry import (
    EARTH_RADIUS_M,
    METERS_PER_MILE,
    bearing_deg,
    cumulative_distances_m,
    destination_point,
    haversine_m,
    perpendicular_offset,
    point_at_distance,
)
from planner.domain.models import LatLon

NEW_YORK = LatLon(40.7128, -74.0060)
LOS_ANGELES = LatLon(34.0522, -118.2437)
LONDON = LatLon(51.5074, -0.1278)
PARIS = LatLon(48.8566, 2.3522)
ORIGIN = LatLon(0.0, 0.0)
ONE_DEGREE_M = EARTH_RADIUS_M * math.pi / 180


def assert_close_pct(actual: float, expected: float, pct: float = 0.5) -> None:
    assert actual == pytest.approx(expected, rel=pct / 100)


class TestHaversine:
    @pytest.mark.parametrize(
        ("a", "b", "expected_m"),
        [
            (NEW_YORK, LOS_ANGELES, 3_935_746.0),
            (LONDON, PARIS, 343_560.0),
            (ORIGIN, LatLon(0.0, 1.0), 111_195.0),
            (ORIGIN, LatLon(1.0, 0.0), 111_195.0),
            (LatLon(-90.0, 0.0), LatLon(90.0, 0.0), math.pi * EARTH_RADIUS_M),
        ],
    )
    def test_matches_known_distances(self, a: LatLon, b: LatLon, expected_m: float) -> None:
        assert_close_pct(haversine_m(a, b), expected_m)

    def test_same_point_is_zero(self) -> None:
        assert haversine_m(NEW_YORK, NEW_YORK) == 0.0

    def test_is_symmetric(self) -> None:
        assert haversine_m(NEW_YORK, LOS_ANGELES) == pytest.approx(
            haversine_m(LOS_ANGELES, NEW_YORK)
        )

    def test_crosses_the_antimeridian_the_short_way(self) -> None:
        distance = haversine_m(LatLon(0.0, 179.5), LatLon(0.0, -179.5))

        assert_close_pct(distance, ONE_DEGREE_M)

    def test_one_mile_constant(self) -> None:
        assert METERS_PER_MILE == 1609.344


class TestCumulativeDistances:
    def test_empty_polyline(self) -> None:
        assert cumulative_distances_m([]) == []

    def test_single_point_is_zero(self) -> None:
        assert cumulative_distances_m([NEW_YORK]) == [0.0]

    def test_accumulates_leg_lengths(self) -> None:
        points = [ORIGIN, LatLon(0.0, 1.0), LatLon(0.0, 3.0)]

        cumulative = cumulative_distances_m(points)

        assert cumulative[0] == 0.0
        assert_close_pct(cumulative[1], ONE_DEGREE_M)
        assert_close_pct(cumulative[2], 3 * ONE_DEGREE_M)


class TestPointAtDistance:
    POINTS = (ORIGIN, LatLon(0.0, 1.0), LatLon(1.0, 1.0))

    def cumulative(self) -> list[float]:
        return cumulative_distances_m(self.POINTS)

    def test_zero_distance_is_the_first_point(self) -> None:
        assert point_at_distance(self.POINTS, self.cumulative(), 0.0) == ORIGIN

    def test_total_distance_is_the_last_point(self) -> None:
        total = self.cumulative()[-1]

        assert point_at_distance(self.POINTS, self.cumulative(), total) == self.POINTS[-1]

    def test_distances_outside_the_route_are_clamped(self) -> None:
        cumulative = self.cumulative()

        assert point_at_distance(self.POINTS, cumulative, -5.0) == ORIGIN
        assert point_at_distance(self.POINTS, cumulative, 1e9) == self.POINTS[-1]

    def test_interpolates_within_a_segment(self) -> None:
        point = point_at_distance(self.POINTS, self.cumulative(), ONE_DEGREE_M / 2)

        assert point.lat == pytest.approx(0.0)
        assert point.lon == pytest.approx(0.5, rel=0.005)

    def test_continues_onto_the_next_segment(self) -> None:
        point = point_at_distance(self.POINTS, self.cumulative(), 1.5 * ONE_DEGREE_M)

        assert point.lon == pytest.approx(1.0)
        assert point.lat == pytest.approx(0.5, rel=0.005)

    def test_exact_vertex_distance_returns_that_vertex(self) -> None:
        cumulative = self.cumulative()

        point = point_at_distance(self.POINTS, cumulative, cumulative[1])

        assert point.lat == pytest.approx(0.0, abs=1e-9)
        assert point.lon == pytest.approx(1.0)

    def test_duplicate_points_do_not_break_interpolation(self) -> None:
        points = [ORIGIN, ORIGIN, LatLon(0.0, 1.0)]
        cumulative = cumulative_distances_m(points)

        point = point_at_distance(points, cumulative, ONE_DEGREE_M / 2)

        assert point.lon == pytest.approx(0.5, rel=0.005)

    def test_single_point_polyline(self) -> None:
        assert point_at_distance([NEW_YORK], [0.0], 100.0) == NEW_YORK

    def test_rejects_empty_polyline(self) -> None:
        with pytest.raises(ValueError, match="no points"):
            point_at_distance([], [], 0.0)

    def test_rejects_mismatched_cumulative_distances(self) -> None:
        with pytest.raises(ValueError, match="differ in length"):
            point_at_distance(self.POINTS, [0.0], 1.0)

    @given(
        st.floats(min_value=0, max_value=1.0),
        st.floats(min_value=0, max_value=1.0),
    )
    def test_distance_from_start_is_monotonic_on_a_straight_route(
        self, fraction_a: float, fraction_b: float
    ) -> None:
        route = [LatLon(30.0, -100.0), LatLon(35.0, -95.0), LatLon(40.0, -90.0)]
        cumulative = cumulative_distances_m(route)
        near, far = sorted((fraction_a, fraction_b))

        p_near = point_at_distance(route, cumulative, near * cumulative[-1])
        p_far = point_at_distance(route, cumulative, far * cumulative[-1])

        assert haversine_m(route[0], p_near) <= haversine_m(route[0], p_far) + 1.0

    @given(st.floats(min_value=0, max_value=1.0), st.floats(min_value=0, max_value=1.0))
    def test_points_are_never_farther_apart_than_the_route_between_them(
        self, fraction_a: float, fraction_b: float
    ) -> None:
        cumulative = self.cumulative()
        total = cumulative[-1]
        d_a, d_b = fraction_a * total, fraction_b * total

        p_a = point_at_distance(self.POINTS, cumulative, d_a)
        p_b = point_at_distance(self.POINTS, cumulative, d_b)

        assert haversine_m(p_a, p_b) <= abs(d_a - d_b) * 1.005 + 1.0


class TestBearing:
    @pytest.mark.parametrize(
        ("target", "expected"),
        [
            (LatLon(1.0, 0.0), 0.0),
            (LatLon(0.0, 1.0), 90.0),
            (LatLon(-1.0, 0.0), 180.0),
            (LatLon(0.0, -1.0), 270.0),
        ],
    )
    def test_cardinal_directions(self, target: LatLon, expected: float) -> None:
        assert bearing_deg(ORIGIN, target) == pytest.approx(expected)

    def test_is_normalised_to_zero_to_360(self) -> None:
        assert 0.0 <= bearing_deg(LOS_ANGELES, NEW_YORK) < 360.0

    def test_new_york_to_los_angeles_heads_west_southwest(self) -> None:
        assert bearing_deg(NEW_YORK, LOS_ANGELES) == pytest.approx(273.7, abs=1.0)


class TestDestinationPoint:
    def test_north_one_degree(self) -> None:
        point = destination_point(ORIGIN, 0.0, ONE_DEGREE_M)

        assert point.lat == pytest.approx(1.0)
        assert point.lon == pytest.approx(0.0, abs=1e-9)

    def test_east_along_the_equator(self) -> None:
        point = destination_point(ORIGIN, 90.0, ONE_DEGREE_M)

        assert point.lat == pytest.approx(0.0, abs=1e-9)
        assert point.lon == pytest.approx(1.0)

    def test_longitude_wraps_over_the_antimeridian(self) -> None:
        point = destination_point(LatLon(0.0, 179.5), 90.0, ONE_DEGREE_M)

        assert point.lon == pytest.approx(-179.5)

    @given(
        st.floats(min_value=-80, max_value=80),
        st.floats(min_value=-179, max_value=179),
        st.floats(min_value=0, max_value=359.9),
        st.floats(min_value=1_000, max_value=500_000),
    )
    def test_distance_and_bearing_round_trip(
        self, lat: float, lon: float, bearing: float, distance_m: float
    ) -> None:
        start = LatLon(lat, lon)

        end = destination_point(start, bearing, distance_m)

        assert haversine_m(start, end) == pytest.approx(distance_m, rel=1e-6)
        difference = abs(bearing_deg(start, end) - bearing)
        assert min(difference, 360 - difference) < 0.01


class TestPerpendicularOffset:
    def test_positive_offset_is_to_the_right_of_the_heading(self) -> None:
        point = perpendicular_offset(ORIGIN, 0.0, 10_000.0)

        assert point.lon > 0.0
        assert point.lat == pytest.approx(0.0, abs=1e-6)
        assert_close_pct(haversine_m(ORIGIN, point), 10_000.0)

    def test_negative_offset_is_to_the_left(self) -> None:
        point = perpendicular_offset(ORIGIN, 0.0, -10_000.0)

        assert point.lon < 0.0
        assert_close_pct(haversine_m(ORIGIN, point), 10_000.0)

    def test_offset_is_at_right_angles_to_the_heading(self) -> None:
        heading = 57.0

        point = perpendicular_offset(NEW_YORK, heading, 20_000.0)

        assert bearing_deg(NEW_YORK, point) == pytest.approx((heading + 90.0) % 360.0, abs=0.01)

    def test_zero_offset_stays_in_place(self) -> None:
        point = perpendicular_offset(NEW_YORK, 123.0, 0.0)

        assert haversine_m(NEW_YORK, point) == pytest.approx(0.0, abs=1e-6)
