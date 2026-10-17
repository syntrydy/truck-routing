from datetime import UTC, datetime, timedelta

import pytest

from planner.domain.corridor import (
    FRAME_COUNT,
    MAX_GRID_POINTS,
    build_frames,
    build_grid,
)
from planner.domain.geometry import destination_point, distance_to_polyline_m
from planner.domain.models import HourlySeries, LatLon
from planner.domain.risk import WindBasis

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

    def test_exactly_200_points_still_fit_the_finest_grid(self) -> None:
        grid = build_grid([straight(DENVER, 90.0, 343 * KM)])  # 200 points at 0.1 degrees

        assert (grid.spacing_deg, len(grid.points)) == (0.1, 200)

    def test_201_points_make_the_grid_coarser(self) -> None:
        grid = build_grid([straight(DENVER, 90.0, 344 * KM)])  # 201 points at 0.1 degrees

        assert grid.spacing_deg == 0.2
        assert len(grid.points) < 200

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


DEPARTURE = datetime(2026, 1, 15, 14, 37, tzinfo=UTC)
FIRST_HOUR = datetime(2026, 1, 15, 14, 0, tzinfo=UTC)


def series(  # noqa: PLR0913 - keyword-only test builder with defaults
    *,
    wind: float | tuple[float, ...] = 0.0,
    gust: float = 0.0,
    rain: float = 0.0,
    snow: float = 0.0,
    start: datetime = FIRST_HOUR,
    hours: int = 60,
) -> HourlySeries:
    winds = wind if isinstance(wind, tuple) else (wind,) * hours
    count = len(winds)
    return HourlySeries(
        start=start,
        wind_mph=winds,
        gust_mph=(gust,) * count,
        rain_in=(rain,) * count,
        showers_in=(0.0,) * count,
        snowfall_in=(snow,) * count,
        weather_code=(0,) * count,
    )


class TestBuildFrames:
    def test_has_49_hourly_frames_from_the_hour_of_departure(self) -> None:
        frames = build_frames([series()], DEPARTURE, load_lb=0)

        assert len(frames) == FRAME_COUNT == 49
        assert frames[0].time == FIRST_HOUR
        assert [b.time - a.time for a, b in zip(frames, frames[1:], strict=False)] == [
            timedelta(hours=1)
        ] * 48

    def test_frames_are_columns_aligned_with_the_points(self) -> None:
        frames = build_frames([series(), series(wind=30.0), None], DEPARTURE, load_lb=0)

        for frame in frames:
            assert len(frame.risk) == len(frame.wind_mph) == len(frame.rain_in_hr) == 3
            assert len(frame.snow_in_hr) == 3

    def test_risk_wind_rain_and_snow_are_reported_per_point(self) -> None:
        calm, windy = series(), series(wind=30.0, rain=0.3, snow=0.6)

        frame = build_frames([calm, windy], DEPARTURE, load_lb=0)[0]

        assert frame.risk == (0, 2)  # LOW; rain 0.3 in/hr is HIGH
        assert frame.wind_mph == (0.0, 30.0)
        assert frame.rain_in_hr == (0.0, 0.3)
        assert frame.snow_in_hr == (0.0, 0.6)

    def test_risk_follows_the_weather_hour_by_hour(self) -> None:
        winds = tuple(float(10 * hour) for hour in range(8))  # 0, 10, ... 70 mph

        frames = build_frames([series(wind=winds)], DEPARTURE, load_lb=0, hours=8)

        assert [frame.risk[0] for frame in frames] == [0, 0, 0, 1, 2, 3, 4, 4]
        assert [frame.wind_mph[0] for frame in frames] == list(winds)

    def test_a_heavy_load_raises_the_risk(self) -> None:
        windy = series(wind=40.0)

        light = build_frames([windy], DEPARTURE, load_lb=20_000)[0]
        heavy = build_frames([windy], DEPARTURE, load_lb=45_000)[0]

        assert light.risk == (2,)  # HIGH
        assert heavy.risk == (3,)  # SEVERE

    def test_gust_basis_assesses_and_reports_the_gust(self) -> None:
        gusty = series(wind=10.0, gust=50.0)

        sustained = build_frames([gusty], DEPARTURE, load_lb=0)[0]
        gust = build_frames([gusty], DEPARTURE, load_lb=0, wind_basis=WindBasis.GUST)[0]

        assert (sustained.risk, sustained.wind_mph) == ((0,), (10.0,))
        assert (gust.risk, gust.wind_mph) == ((3,), (50.0,))

    def test_a_point_without_weather_is_unknown(self) -> None:
        frame = build_frames([series(wind=30.0), None], DEPARTURE, load_lb=0)[0]

        assert frame.risk == (1, -1)
        assert frame.wind_mph == (30.0, None)
        assert frame.rain_in_hr == (0.0, None)
        assert frame.snow_in_hr == (0.0, None)

    def test_hours_beyond_the_series_are_unknown(self) -> None:
        short = series(wind=tuple(30.0 for _ in range(5)))  # 14:00 .. 18:00

        frames = build_frames([short], DEPARTURE, load_lb=0, hours=8)

        assert [frame.risk[0] for frame in frames] == [1, 1, 1, 1, 1, -1, -1, -1]
        assert frames[-1].wind_mph == (None,)

    def test_series_starting_before_the_departure_hour_is_aligned_by_time(self) -> None:
        early = series(
            wind=tuple(float(10 * hour) for hour in range(10)),
            start=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        )

        frames = build_frames([early], DEPARTURE, load_lb=0, hours=2)

        assert [frame.wind_mph[0] for frame in frames] == [20.0, 30.0]  # 14:00 and 15:00

    def test_hours_can_be_limited(self) -> None:
        assert len(build_frames([series()], DEPARTURE, load_lb=0, hours=3)) == 3

    def test_no_points_gives_empty_frames(self) -> None:
        frames = build_frames([], DEPARTURE, load_lb=0, hours=2)

        assert [frame.risk for frame in frames] == [(), ()]

    def test_departure_must_be_timezone_aware(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            build_frames([series()], datetime(2026, 1, 15, 14, 37), load_lb=0)  # noqa: DTZ001
