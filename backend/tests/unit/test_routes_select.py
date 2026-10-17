import time

import pytest

from planner.domain.geometry import (
    cumulative_distances_m,
    destination_point,
    haversine_m,
)
from planner.domain.models import LatLon
from planner.domain.routes_select import (
    MAX_ROUTES,
    RouteCandidate,
    select_routes,
    via_points,
)

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


def candidate(
    route_id: str,
    points: list[LatLon],
    duration_s: float,
    *,
    is_detour: bool = False,
    distance_m: float | None = None,
) -> RouteCandidate:
    length = cumulative_distances_m(points)[-1] if distance_m is None else distance_m
    return RouteCandidate(route_id, points, length, duration_s, is_detour)


def base(duration_s: float = 3_600.0) -> RouteCandidate:
    return candidate("base", line(START, EAST, 100 * KM), duration_s)


def parallel(route_id: str, offset_m: float, duration_s: float, **kwargs: object) -> RouteCandidate:
    origin = destination_point(START, NORTH, offset_m)
    return candidate(route_id, line(origin, EAST, 100 * KM), duration_s, **kwargs)  # type: ignore[arg-type]


def shares_then_leaves(route_id: str, shared_share: float, duration_s: float) -> RouteCandidate:
    """Follows the base route for a share of its length, then turns north."""
    shared_m = shared_share * 100 * KM
    corner = destination_point(START, EAST, shared_m)
    points = [*line(START, EAST, shared_m), *line(corner, NORTH, 100 * KM - shared_m)[1:]]
    return candidate(route_id, points, duration_s)


def ids(selection_routes: tuple[RouteCandidate, ...]) -> list[str]:
    return [route.route_id for route in selection_routes]


class TestDeduplication:
    def test_identical_routes_are_collapsed(self) -> None:
        twin = candidate("twin", line(START, EAST, 100 * KM), 3_700.0)

        selection = select_routes([base(), twin])

        assert ids(selection.routes) == ["base"]

    def test_route_half_a_kilometer_away_is_a_duplicate(self) -> None:
        assert ids(select_routes([base(), parallel("near", 500.0, 3_700.0)]).routes) == ["base"]

    def test_route_five_kilometers_away_is_distinct(self) -> None:
        selection = select_routes([base(), parallel("apart", 5 * KM, 3_700.0)])

        assert ids(selection.routes) == ["base", "apart"]

    def test_route_sharing_90_percent_is_a_duplicate(self) -> None:
        selection = select_routes([base(), shares_then_leaves("mostly-same", 0.9, 3_700.0)])

        assert ids(selection.routes) == ["base"]

    def test_route_sharing_70_percent_is_distinct(self) -> None:
        selection = select_routes([base(), shares_then_leaves("diverges", 0.7, 3_700.0)])

        assert ids(selection.routes) == ["base", "diverges"]

    def test_overlap_is_measured_against_all_kept_routes_together(self) -> None:
        north = parallel("north", 10 * KM, 3_800.0)
        hop = [
            *line(START, EAST, 50 * KM),
            *line(destination_point(START, EAST, 50 * KM), NORTH, 10 * KM)[1:],
            *line(
                destination_point(destination_point(START, EAST, 50 * KM), NORTH, 10 * KM),
                EAST,
                50 * KM,
            )[1:],
        ]
        mixed = candidate("mixed", hop, 3_900.0)

        selection = select_routes([base(), north, mixed])

        assert ids(selection.routes) == ["base", "north"]

    @pytest.mark.parametrize("offset_m", [600.0, 900.0, 1_000.0])
    def test_proximity_is_measured_in_kilometers_east_west_too(self, offset_m: float) -> None:
        north_south = candidate("ns", line(START, NORTH, 100 * KM), 3_600.0)
        east = destination_point(START, EAST, offset_m)
        twin = candidate("twin", line(east, NORTH, 100 * KM), 3_700.0)

        assert ids(select_routes([north_south, twin]).routes) == ["ns"]

    def test_the_end_of_a_route_counts_as_a_sample(self) -> None:
        main = candidate("main", line(START, EAST, 100 * KM), 3_600.0)
        spur = candidate("spur", [START, destination_point(START, NORTH, 1_500.0)], 3_700.0)

        selection = select_routes([main, spur])

        assert ids(selection.routes) == ["main", "spur"]

    def test_the_fastest_route_is_kept_when_listed_last(self) -> None:
        slower_twin = candidate("slow", line(START, EAST, 100 * KM), 4_000.0)

        selection = select_routes([slower_twin, base(3_600.0)])

        assert ids(selection.routes) == ["base"]


class TestDetourLength:
    def detour(self, distance_m: float, *, is_detour: bool = True) -> RouteCandidate:
        via = destination_point(destination_point(START, EAST, 50 * KM), NORTH, 30 * KM)
        points = [START, via, destination_point(START, EAST, 100 * KM)]
        return candidate("detour", points, 4_000.0, is_detour=is_detour, distance_m=distance_m)

    def fastest(self) -> RouteCandidate:
        return candidate("fastest", line(START, EAST, 100 * KM), 3_600.0, distance_m=100_000.0)

    def test_detour_more_than_40_percent_longer_is_rejected(self) -> None:
        selection = select_routes([self.fastest(), self.detour(140_001.0)])

        assert ids(selection.routes) == ["fastest"]

    def test_detour_exactly_40_percent_longer_is_kept(self) -> None:
        selection = select_routes([self.fastest(), self.detour(140_000.0)])

        assert ids(selection.routes) == ["fastest", "detour"]

    def test_provider_alternative_is_not_subject_to_the_length_limit(self) -> None:
        selection = select_routes([self.fastest(), self.detour(160_000.0, is_detour=False)])

        assert ids(selection.routes) == ["fastest", "detour"]


class TestLimitAndOrder:
    def test_at_most_three_routes_are_returned(self) -> None:
        routes = [base(3_600.0)] + [
            parallel(f"r{n}", n * 10 * KM, 3_600.0 + n * 100.0) for n in range(1, 6)
        ]

        selection = select_routes(routes)

        assert len(selection.routes) == MAX_ROUTES
        assert ids(selection.routes) == ["base", "r1", "r2"]

    def test_routes_are_ordered_by_duration_whatever_the_input_order(self) -> None:
        slow = parallel("slow", 10 * KM, 5_000.0)
        medium = parallel("medium", 20 * KM, 4_000.0)

        selection = select_routes([slow, medium, base()])

        assert ids(selection.routes) == ["base", "medium", "slow"]

    def test_equal_durations_keep_the_given_order(self) -> None:
        a = parallel("a", 10 * KM, 3_600.0)
        b = parallel("b", 20 * KM, 3_600.0)

        assert ids(select_routes([a, b]).routes) == ["a", "b"]

    def test_a_single_candidate_is_returned_as_is(self) -> None:
        assert ids(select_routes([base()]).routes) == ["base"]

    def test_no_candidates_is_an_error(self) -> None:
        with pytest.raises(ValueError, match="no candidate"):
            select_routes([])

    def test_a_candidate_needs_two_points(self) -> None:
        with pytest.raises(ValueError, match="two points"):
            RouteCandidate("bad", [START], 0.0, 0.0)


class TestNotes:
    def test_three_routes_need_no_note(self) -> None:
        selection = select_routes(
            [base(), parallel("b", 10 * KM, 3_700.0), parallel("c", 20 * KM, 3_800.0)]
        )

        assert selection.notes == ()

    def test_two_routes_get_a_note(self) -> None:
        selection = select_routes([base(), parallel("b", 10 * KM, 3_700.0)])

        assert selection.notes == ("Only 2 distinct routes exist for this trip",)

    def test_a_single_route_gets_a_singular_note(self) -> None:
        twin = candidate("twin", line(START, EAST, 100 * KM), 3_700.0)

        selection = select_routes([base(), twin])

        assert selection.notes == ("Only 1 distinct route exists for this trip",)

    def test_duplicates_are_never_added_to_reach_three(self) -> None:
        twin = candidate("twin", line(START, EAST, 100 * KM), 3_700.0)

        selection = select_routes([base(), twin, twin, twin])

        assert ids(selection.routes) == ["base"]


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


def test_selection_is_fast_on_cross_country_routes() -> None:
    far = LatLon(36.0, -75.0)
    count = 20_000
    main = [
        LatLon(34.0 + (far.lat - 34.0) * i / count, -120.0 + (far.lon + 120.0) * i / count)
        for i in range(count + 1)
    ]
    shifted = [LatLon(p.lat + 0.3, p.lon) for p in main]
    near_copy = [LatLon(p.lat + 0.001, p.lon) for p in main]
    candidates = [
        candidate("main", main, 100_000.0),
        candidate("shifted", shifted, 101_000.0),
        candidate("copy", near_copy, 102_000.0),
    ]

    started = time.perf_counter()
    selection = select_routes(candidates)
    elapsed = time.perf_counter() - started

    assert ids(selection.routes) == ["main", "shifted"]
    assert elapsed < 10.0
