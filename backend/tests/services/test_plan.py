from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from planner.domain.geometry import METERS_PER_MILE, destination_point, haversine_m
from planner.domain.models import LatLon, RiskLevel
from planner.domain.risk import WindBasis
from planner.providers.protocols import ProviderRoute, rounded_point
from planner.services.models import PlanBanner, PlanRequest
from planner.services.plan import PlanService
from tests.infra.fakes import FakeClock
from tests.services.stubs import START, StubRouting, StubWeather, route

DEPARTURE = datetime(2026, 10, 18, 14, 0, tzinfo=UTC)
NOW = datetime(2026, 10, 18, 13, 55, tzinfo=UTC)
NORTH, SOUTH = 0.0, 180.0


def three_routes() -> list[ProviderRoute]:
    """A straight route and two parallel ones about 20 km north and south of it."""
    middle = route(60, 55)
    north = route(62, 52, origin=destination_point(START, NORTH, 20_000))
    south = route(65, 50, origin=destination_point(START, SOUTH, 20_000))
    return [middle, north, south]


def with_neighbours(main: ProviderRoute) -> list[ProviderRoute]:
    """``main`` and two slower routes 20 km to its north and south, so none is a duplicate."""
    north = route(70, 40, origin=destination_point(START, NORTH, 20_000))
    south = route(75, 38, origin=destination_point(START, SOUTH, 20_000))
    return [main, north, south]


def request_for(provider_route: ProviderRoute, **changes: object) -> PlanRequest:
    request = PlanRequest(
        origin=provider_route.points[0],
        destination=provider_route.points[-1],
        departure=DEPARTURE,
        load_lb=20_000,
        interval_mi=25,
    )
    return replace(request, **changes)  # type: ignore[arg-type]


def make_service(
    routing: StubRouting, weather: StubWeather, clock: FakeClock | None = None, **kwargs: object
) -> PlanService:
    clock = clock or FakeClock()
    return PlanService(
        routing,
        weather,
        max_speed_mph=65.0,
        wind_basis=kwargs.pop("wind_basis", WindBasis.SUSTAINED),  # type: ignore[arg-type]
        now=lambda: NOW,
        monotonic=clock,
        **kwargs,  # type: ignore[arg-type]
    )


def storm_on_the_middle_route(place: LatLon) -> dict[str, float]:
    """Severe wind only around latitude 40.0, where the middle route runs."""
    return {"wind": 50.0, "gust": 60.0} if place.lat == 40.0 else {}


class TestAFullPlan:
    def test_three_provider_routes_are_ranked_and_one_is_recommended(self) -> None:
        routes = three_routes()
        service = make_service(StubRouting(routes), StubWeather())

        result = service.plan(request_for(routes[0]))

        assert len(result.routes) == 3
        assert [r.rank for r in result.routes] == [1, 2, 3]
        assert result.recommended_route_id == result.routes[0].id
        assert result.recommendation_reason is not None
        assert result.banner is None

    def test_routes_get_ids_and_labels_in_order_of_speed(self) -> None:
        routes = three_routes()
        service = make_service(StubRouting(routes), StubWeather())

        result = service.plan(request_for(routes[0]))

        by_id = {r.id: r for r in result.routes}
        assert set(by_id) == {"r1", "r2", "r3"}
        assert [by_id[i].label for i in ("r1", "r2", "r3")] == ["Route A", "Route B", "Route C"]
        durations = [by_id[i].duration_s for i in ("r1", "r2", "r3")]
        assert durations == sorted(durations)

    def test_calm_weather_makes_every_checkpoint_low(self) -> None:
        routes = three_routes()
        service = make_service(StubRouting(routes), StubWeather())

        result = service.plan(request_for(routes[0]))

        for planned in result.routes:
            assert {c.level for c in planned.checkpoints} == {RiskLevel.LOW}
            assert planned.score.unknown_miles == 0
            assert not planned.score.low_confidence

    def test_checkpoints_follow_the_interval_and_end_at_the_destination(self) -> None:
        routes = three_routes()
        service = make_service(StubRouting([routes[0], routes[1], routes[2]]), StubWeather())

        planned = service.plan(request_for(routes[0], interval_mi=25)).routes
        middle = next(r for r in planned if r.label == "Route A")

        assert [round(c.distance_mi) for c in middle.checkpoints] == [0, 25, 50, 60]
        assert middle.checkpoints[-1].location == middle.points[-1]
        assert middle.checkpoints[0].eta == DEPARTURE

    def test_each_checkpoint_carries_the_weather_at_its_eta(self) -> None:
        routes = three_routes()
        weather = StubWeather(lambda place: {"wind": 12.0, "gust": 20.0, "rain": 0.0})
        service = make_service(StubRouting(routes), weather)

        checkpoint = service.plan(request_for(routes[0])).routes[0].checkpoints[1]

        assert checkpoint.weather is not None
        assert checkpoint.weather.wind_mph == 12.0
        assert checkpoint.weather.gust_mph == 20.0

    def test_a_storm_on_one_route_moves_the_recommendation_to_a_calm_one(self) -> None:
        routes = three_routes()
        service = make_service(StubRouting(routes), StubWeather(storm_on_the_middle_route))

        result = service.plan(request_for(routes[0]))

        stormy = next(r for r in result.routes if r.label == "Route A")
        assert stormy.score.miles_by_level[RiskLevel.SEVERE] > 0
        assert result.recommended_route_id != stormy.id
        assert result.recommended_route_id == result.routes[0].id
        assert stormy.rank == 3  # the two calm routes come first
        assert result.recommendation_reason is not None
        # The reason compares the winner with the runner-up (both calm), so it is about time.
        assert "fastest" in result.recommendation_reason

    def test_a_heavy_load_turns_severe_wind_into_no_travel(self) -> None:
        routes = three_routes()
        service = make_service(StubRouting(routes), StubWeather(storm_on_the_middle_route))

        result = service.plan(request_for(routes[0], load_lb=45_000))

        stormy = next(r for r in result.routes if r.label == "Route A")
        assert stormy.score.miles_by_level[RiskLevel.NO_TRAVEL] > 0
        assert result.recommended_route_id != stormy.id

    def test_the_wind_basis_decides_between_sustained_and_gust(self) -> None:
        routes = three_routes()
        gusty = StubWeather(lambda place: {"wind": 10.0, "gust": 50.0})

        sustained = make_service(StubRouting(routes), gusty).plan(request_for(routes[0]))
        gust = make_service(StubRouting(routes), gusty, wind_basis=WindBasis.GUST).plan(
            request_for(routes[0])
        )

        assert sustained.routes[0].score.worst_level is RiskLevel.LOW
        assert gust.routes[0].score.worst_level is RiskLevel.SEVERE

    def test_the_result_says_where_the_data_came_from(self) -> None:
        routes = three_routes()
        service = make_service(StubRouting(routes, source="openrouteservice"), StubWeather())

        meta = service.plan(request_for(routes[0])).meta

        assert (meta.routing_source, meta.weather_source) == ("openrouteservice", "stub-weather")
        assert meta.weather_stale is False
        assert meta.generated_at == NOW


class TestTruckTimes:
    def test_segment_times_are_scaled_up_to_the_providers_route_total(self) -> None:
        slow = route(60, 50, delay_share=0.10)  # segment times 10% short of the route total
        service = make_service(StubRouting(with_neighbours(slow)), StubWeather())

        planned = service.plan(request_for(slow)).routes
        match = next(r for r in planned if r.distance_mi == pytest.approx(60, rel=0.01))

        assert match.duration_s == pytest.approx(slow.duration_s, rel=1e-6)
        assert match.checkpoints[-1].eta - DEPARTURE == timedelta(seconds=match.duration_s)

    def test_times_are_never_scaled_down(self) -> None:
        fast_total = route(60, 50)
        shorter_total = ProviderRoute(
            points=fast_total.points,
            distance_m=fast_total.distance_m,
            duration_s=sum(fast_total.segment_durations_s) * 0.5,  # total below the segments
            segment_durations_s=fast_total.segment_durations_s,
            segment_distances_m=fast_total.segment_distances_m,
        )
        service = make_service(
            StubRouting([shorter_total, route(61, 50), route(62, 50)]), StubWeather()
        )

        planned = service.plan(request_for(shorter_total)).routes
        match = next(r for r in planned if r.distance_mi == pytest.approx(60, rel=0.01))

        assert match.duration_s == pytest.approx(sum(fast_total.segment_durations_s), rel=1e-6)

    def test_the_truck_speed_limit_slows_a_fast_route(self) -> None:
        fast = route(130, 100, delay_share=0.0)
        service = make_service(StubRouting(with_neighbours(fast)), StubWeather())

        planned = service.plan(request_for(fast)).routes
        match = next(r for r in planned if r.distance_mi == pytest.approx(130, rel=0.01))

        assert match.duration_s == pytest.approx(130 / 65 * 3_600, rel=0.01)

    def test_the_distance_is_the_length_of_the_geometry(self) -> None:
        routes = three_routes()
        service = make_service(StubRouting(routes), StubWeather())

        planned = service.plan(request_for(routes[0])).routes
        match = next(r for r in planned if r.label == "Route A")

        expected = sum(
            haversine_m(a, b) for a, b in zip(match.points, match.points[1:], strict=False)
        )
        assert match.distance_mi == pytest.approx(expected / METERS_PER_MILE)
        assert match.checkpoints[-1].distance_mi == pytest.approx(match.distance_mi)


class TestWeatherLookup:
    def test_one_lookup_covers_the_checkpoints_and_the_heatmap_grid(self) -> None:
        routes = three_routes()
        weather = StubWeather()
        service = make_service(StubRouting(routes), weather)

        result = service.plan(request_for(routes[0]))

        assert len(weather.calls) == 1
        asked = {rounded_point(p) for p in weather.calls[0][0]}
        for planned in result.routes:
            assert {rounded_point(c.location) for c in planned.checkpoints} <= asked
        assert {rounded_point(p) for p in result.heatmap.points} <= asked

    def test_the_days_asked_for_cover_the_departure_and_the_heatmap_window(self) -> None:
        routes = three_routes()
        weather = StubWeather()
        service = make_service(StubRouting(routes), weather)

        service.plan(request_for(routes[0]))

        _, first_day, last_day = weather.calls[0]
        assert first_day == date(2026, 10, 18)
        assert last_day == date(2026, 10, 20)  # 14:00 on the 18th plus 48 hours

    def test_a_late_departure_asks_for_the_extra_day(self) -> None:
        routes = three_routes()
        weather = StubWeather()
        service = make_service(StubRouting(routes), weather)
        late = request_for(routes[0], departure=datetime(2026, 10, 18, 23, 30, tzinfo=UTC))

        service.plan(late)

        assert weather.calls[0][2] == date(2026, 10, 20)

    def test_a_departure_with_an_offset_is_looked_up_in_utc(self) -> None:
        routes = three_routes()
        weather = StubWeather()
        service = make_service(StubRouting(routes), weather)
        evening_in_denver = request_for(
            routes[0], departure=datetime(2026, 10, 18, 20, 0, tzinfo=timezone(timedelta(hours=-6)))
        )

        service.plan(evening_in_denver)

        assert weather.calls[0][1] == date(2026, 10, 19)  # 02:00 UTC on the 19th

    def test_a_very_long_trip_is_limited_to_the_forecast_horizon(self) -> None:
        crawl = route(30, 0.05)  # 600 hours of driving, 25 days
        weather = StubWeather()
        service = make_service(StubRouting(with_neighbours(crawl)), weather)

        service.plan(request_for(crawl, interval_mi=10))

        first_day, last_day = weather.calls[0][1], weather.calls[0][2]
        assert (last_day - first_day).days == 15


class TestHeatmap:
    def test_it_has_49_hourly_frames_over_the_grid(self) -> None:
        routes = three_routes()
        service = make_service(StubRouting(routes), StubWeather())

        heatmap = service.plan(request_for(routes[0])).heatmap

        assert heatmap.start == DEPARTURE
        assert len(heatmap.frames) == 49
        assert heatmap.points
        assert all(len(frame.risk) == len(heatmap.points) for frame in heatmap.frames)

    def test_the_start_is_the_hour_of_departure(self) -> None:
        routes = three_routes()
        service = make_service(StubRouting(routes), StubWeather())

        heatmap = service.plan(
            request_for(routes[0], departure=datetime(2026, 10, 18, 14, 41, tzinfo=UTC))
        ).heatmap

        assert heatmap.start == DEPARTURE
        assert heatmap.frames[1].time - heatmap.frames[0].time == timedelta(hours=1)

    def test_the_storm_shows_in_the_frames(self) -> None:
        routes = three_routes()
        service = make_service(StubRouting(routes), StubWeather(storm_on_the_middle_route))

        heatmap = service.plan(request_for(routes[0])).heatmap

        assert max(heatmap.frames[0].risk) == int(RiskLevel.SEVERE)
        assert min(heatmap.frames[0].risk) == int(RiskLevel.LOW)


class TestWeatherGaps:
    """Missing weather matters where a route passes; on the map alone it is only a note."""

    def checkpoint_places(self, routes: list[ProviderRoute]) -> set[LatLon]:
        calm = make_service(StubRouting(routes), StubWeather()).plan(request_for(routes[0]))
        return {rounded_point(c.location) for r in calm.routes for c in r.checkpoints}

    def test_gaps_only_among_the_heatmap_cells_raise_no_banner(self) -> None:
        routes = three_routes()
        on_routes = self.checkpoint_places(routes)
        weather = StubWeather(lambda place: {} if place in on_routes else None)
        service = make_service(StubRouting(routes), weather)

        result = service.plan(request_for(routes[0]))

        assert result.banner is None
        assert all(not r.score.low_confidence for r in result.routes)
        assert {c.level for r in result.routes for c in r.checkpoints} == {RiskLevel.LOW}
        [note] = [n for n in result.notes if "weather map" in n]
        assert "have no forecast" in note

    def test_a_gap_at_a_checkpoint_raises_the_banner_and_counts_only_checkpoints(self) -> None:
        routes = three_routes()
        on_routes = sorted(self.checkpoint_places(routes), key=lambda p: (p.lat, p.lon))
        lost = on_routes[0]
        weather = StubWeather(lambda place: None if place == lost else {})
        service = make_service(StubRouting(routes), weather)

        result = service.plan(request_for(routes[0]))

        assert result.banner is PlanBanner.WEATHER_UNAVAILABLE
        assert "Weather is unavailable for 1 location; their risk is shown as unknown" in (
            result.notes
        )
        assert not any("weather map" in n for n in result.notes)

    def test_no_weather_at_all_counts_checkpoints_and_cells_apart(self) -> None:
        routes = three_routes()
        on_routes = self.checkpoint_places(routes)
        service = make_service(StubRouting(routes), StubWeather(lambda place: None))

        result = service.plan(request_for(routes[0]))

        cells = {rounded_point(p) for p in result.heatmap.points} - on_routes
        assert result.banner is PlanBanner.WEATHER_UNAVAILABLE
        assert (
            f"Weather is unavailable for {len(on_routes)} locations; their risk is shown as unknown"
            in (result.notes)
        )
        assert (
            f"{len(cells)} cells of the weather map have no forecast; they are shown in grey"
            in (result.notes)
        )
