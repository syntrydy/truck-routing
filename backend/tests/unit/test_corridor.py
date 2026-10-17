import pytest

from planner.domain.corridor import (
    MAX_GRID_POINTS,
    build_grid,
)
from planner.domain.geometry import destination_point, distance_to_polyline_m
from planner.domain.models import LatLon

DENVER = LatLon(39.7392, -104.9903)
KM = 1_000.0
CORRIDOR_RADIUS_M = 25_000.0  # fixed here on purpose: the spec value, not the module constant
WITHIN_25_KM = CORRIDOR_RADIUS_M * 1.001


def straight(
    origin: LatLon, bearing: float, length_m: float, step_m: float = 5 * KM
) -> list[LatLon]:
    count = max(int(length_m // step_m), 1)
    return [destination_point(origin, bearing, length_m * i / count) for i in range(count + 1)]


def los_angeles_to_new_york() -> list[LatLon]:
    count = 400
    start, end = LatLon(34.05, -118.24), LatLon(40.71, -74.0)
    return [
        LatLon(
            start.lat + (end.lat - start.lat) * i / count,
            start.lon + (end.lon - start.lon) * i / count,
        )
        for i in range(count + 1)
    ]


def assert_all_within_corridor(points: tuple[LatLon, ...], routes: list[list[LatLon]]) -> None:
    for point in points:
        nearest = min(distance_to_polyline_m(point, route) for route in routes)
        assert nearest <= WITHIN_25_KM, f"{point} is {nearest / KM:.1f} km from the nearest route"


class TestBuildGrid:
    def test_short_route_has_a_fine_grid_of_at_least_20_points(self) -> None:
        route = straight(DENVER, 90.0, 48 * KM)  # about 30 miles

        grid = build_grid([route])

        assert 20 <= len(grid.points) <= MAX_GRID_POINTS
        assert grid.spacing_deg == 0.1
        assert_all_within_corridor(grid.points, [route])

    def test_cross_country_route_stays_within_200_points(self) -> None:
        route = los_angeles_to_new_york()

        grid = build_grid([route])

        assert 20 <= len(grid.points) <= MAX_GRID_POINTS
        assert grid.spacing_deg > 0.1
        assert_all_within_corridor(grid.points, [route])

    def test_cross_country_grid_is_not_needlessly_sparse(self) -> None:
        grid = build_grid([los_angeles_to_new_york()])

        assert len(grid.points) >= 100

    def test_spacing_is_the_finest_that_fits(self) -> None:
        route = straight(DENVER, 90.0, 400 * KM)

        grid = build_grid([route])

        assert grid.spacing_deg == 0.2
        finer = _brute_force_count(route, spacing=0.1)
        assert finer > MAX_GRID_POINTS

    def test_spacing_is_a_doubling_of_the_start_spacing(self) -> None:
        for length_km in (30, 400, 1_500):
            spacing = build_grid([straight(DENVER, 90.0, length_km * KM)]).spacing_deg
            assert spacing in {0.1 * 2**n for n in range(8)}

    def test_points_sit_on_multiples_of_the_spacing(self) -> None:
        grid = build_grid([straight(DENVER, 60.0, 300 * KM)])

        for point in grid.points:
            for coordinate in (point.lat, point.lon):
                steps = coordinate / grid.spacing_deg
                assert steps == pytest.approx(round(steps), abs=1e-6)

    def test_points_are_ordered_by_latitude_then_longitude(self) -> None:
        grid = build_grid([straight(DENVER, 45.0, 200 * KM)])

        assert list(grid.points) == sorted(grid.points, key=lambda p: (p.lat, p.lon))
        assert len(set(grid.points)) == len(grid.points)

    def test_the_grid_is_deterministic(self) -> None:
        routes = [straight(DENVER, 45.0, 200 * KM)]

        assert build_grid(routes) == build_grid(routes)

    def test_covers_every_route_not_just_the_first(self) -> None:
        north = straight(DENVER, 90.0, 80 * KM)
        south_start = destination_point(DENVER, 180.0, 150 * KM)
        south = straight(south_start, 90.0, 80 * KM)

        grid = build_grid([north, south])

        assert_all_within_corridor(grid.points, [north, south])
        assert any(distance_to_polyline_m(p, north) <= WITHIN_25_KM for p in grid.points)
        assert any(distance_to_polyline_m(p, south) <= WITHIN_25_KM for p in grid.points)
        assert not any(
            distance_to_polyline_m(p, north) > WITHIN_25_KM
            and distance_to_polyline_m(p, south) > WITHIN_25_KM
            for p in grid.points
        )

    def test_a_degenerate_route_still_gets_a_neighbourhood(self) -> None:
        grid = build_grid([[DENVER, DENVER]])

        assert 1 <= len(grid.points) <= MAX_GRID_POINTS
        assert_all_within_corridor(grid.points, [[DENVER, DENVER]])

    def test_coordinates_stay_valid_near_the_antimeridian_and_poles(self) -> None:
        route = [LatLon(88.0, 179.9), LatLon(88.5, 179.95)]

        grid = build_grid([route])

        assert grid.points
        assert all(-90 <= p.lat <= 90 and -180 <= p.lon <= 180 for p in grid.points)

    @pytest.mark.parametrize(
        "origin", [DENVER, LatLon(60.0, 10.0)], ids=["mid-latitude", "60-north"]
    )
    def test_no_point_inside_the_corridor_is_missing(self, origin: LatLon) -> None:
        route = straight(origin, 90.0, 60 * KM)

        grid = build_grid([route])

        expected = _brute_force_points(route, grid.spacing_deg, radius_m=24_900.0)
        assert expected
        assert expected <= set(grid.points)

    def test_the_point_limit_is_inclusive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        route = straight(DENVER, 90.0, 400 * KM)
        count = len(build_grid([route]).points)

        monkeypatch.setattr("planner.domain.corridor.MAX_GRID_POINTS", count)
        at_limit = build_grid([route])
        monkeypatch.setattr("planner.domain.corridor.MAX_GRID_POINTS", count - 1)
        below_limit = build_grid([route])

        assert len(at_limit.points) == count
        assert below_limit.spacing_deg == pytest.approx(2 * at_limit.spacing_deg)

    @pytest.mark.parametrize("routes", [[], [[]], [[DENVER, DENVER], []]])
    def test_rejects_missing_routes(self, routes: list[list[LatLon]]) -> None:
        with pytest.raises(ValueError, match="at least one point"):
            build_grid(routes)


def _brute_force_points(route: list[LatLon], spacing: float, radius_m: float) -> set[LatLon]:
    """Lattice points within ``radius_m`` of the route, found the slow, exact way."""
    lats = [p.lat for p in route]
    lons = [p.lon for p in route]
    found: set[LatLon] = set()
    for row in range(int((min(lats) - 1) / spacing), int((max(lats) + 1) / spacing) + 1):
        for col in range(int((min(lons) - 2) / spacing), int((max(lons) + 2) / spacing) + 1):
            point = LatLon(round(row * spacing, 6), round(col * spacing, 6))
            if distance_to_polyline_m(point, route) <= radius_m:
                found.add(point)
    return found


def _brute_force_count(route: list[LatLon], spacing: float) -> int:
    """Lattice points within 25 km of the route, found the slow, exact way."""
    lats = [d.lat for d in route]
    lons = [d.lon for d in route]
    count = 0
    lat_steps = range(int((min(lats) - 0.5) / spacing), int((max(lats) + 0.5) / spacing) + 1)
    lon_steps = range(int((min(lons) - 0.7) / spacing), int((max(lons) + 0.7) / spacing) + 1)
    for row in lat_steps:
        for col in lon_steps:
            point = LatLon(row * spacing, col * spacing)
            if distance_to_polyline_m(point, route) <= CORRIDOR_RADIUS_M:
                count += 1
    return count
