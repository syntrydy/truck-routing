from datetime import UTC, datetime, timedelta, timezone

import pytest

from planner.domain.geometry import destination_point, haversine_m
from planner.domain.models import LatLon, RiskLevel
from planner.infra.errors import (
    UpstreamContractError,
    UpstreamError,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from planner.infra.resilience import current_deadline
from planner.providers.protocols import NoRoute, ProviderRoute
from planner.services.models import PlanBanner, PlanRequest, TooClose
from tests.infra.fakes import FakeClock
from tests.services.stubs import START, StubRouting, StubWeather, route
from tests.services.test_plan import (
    DEPARTURE,
    NORTH,
    SOUTH,
    make_service,
    request_for,
    three_routes,
)

FAR_NORTH = 40_000.0


def offset_route(
    length_mi: float, mph: float, side: float, meters: float = 20_000.0
) -> ProviderRoute:
    return route(length_mi, mph, origin=destination_point(START, side, meters))


class TestDetours:
    def test_with_fewer_than_three_routes_detours_are_asked_for_on_both_sides(self) -> None:
        main = route(60, 55)
        routing = StubRouting(
            [main],
            via=lambda via: [
                route(
                    64,
                    50,
                    origin=destination_point(
                        START, NORTH if via.lat > START.lat else SOUTH, 25_000
                    ),
                )
            ],
        )
        service = make_service(routing, StubWeather())

        result = service.plan(request_for(main))

        asks = [call for call in routing.calls if call[0] == "route_via"]
        assert len(asks) == 2
        vias = [call[1][1] for call in asks]
        assert min(v.lat for v in vias) < START.lat < max(v.lat for v in vias)
        assert len(result.routes) == 3
        assert result.notes == ("ETAs assume continuous driving at ≤ 65 mph",)

    def test_detour_points_are_placed_around_the_middle_of_the_fastest_route(self) -> None:
        fast = route(60, 55)
        slow = route(70, 40, origin=destination_point(START, NORTH, 60_000))  # 60 km further north
        routing = StubRouting([slow, fast], via=lambda via: [])
        service = make_service(routing, StubWeather())

        service.plan(request_for(fast))

        vias = [call[1][1] for call in routing.calls if call[0] == "route_via"]
        middle_lat = sum(v.lat for v in vias) / len(vias)
        assert middle_lat == pytest.approx(fast.points[len(fast.points) // 2].lat, abs=0.02)

    def test_a_long_alternative_from_the_provider_is_kept_unlike_a_long_detour(self) -> None:
        fast = route(60, 55)
        long_alternative = route(100, 60, origin=destination_point(START, NORTH, 25_000))
        routing = StubRouting([fast, long_alternative], via=lambda via: [])
        service = make_service(routing, StubWeather())

        result = service.plan(request_for(fast))

        assert len(result.routes) == 2  # 67% longer, but the provider offered it itself

    def test_detours_start_and_end_at_the_requested_points(self) -> None:
        main = route(60, 55)
        routing = StubRouting([main], via=lambda via: [])
        service = make_service(routing, StubWeather())
        request = request_for(main)

        service.plan(request)

        for kind, points in routing.calls:
            assert points[0] == request.origin
            assert points[-1] == request.destination
            assert kind in {"routes", "route_via"}

    def test_three_routes_from_the_provider_need_no_detours(self) -> None:
        routing = StubRouting(three_routes())
        service = make_service(routing, StubWeather())

        service.plan(request_for(three_routes()[0]))

        assert [kind for kind, _ in routing.calls] == ["routes"]

    def test_a_detour_that_is_much_longer_is_not_offered(self) -> None:
        main = route(60, 55)
        routing = StubRouting(
            [main], via=lambda via: [route(100, 55, origin=destination_point(START, NORTH, 25_000))]
        )
        service = make_service(routing, StubWeather())

        result = service.plan(request_for(main))

        assert len(result.routes) == 1
        assert "Only 1 distinct route exists for this trip" in result.notes

    def test_fewer_than_three_distinct_routes_say_so(self) -> None:
        main = route(60, 55)
        service = make_service(StubRouting([main], via=lambda via: []), StubWeather())

        result = service.plan(request_for(main))

        assert "Only 1 distinct route exists for this trip" in result.notes

    @pytest.mark.parametrize(
        "failure",
        [
            UpstreamUnavailable("osrm", "down"),
            UpstreamTimeout("osrm", "slow"),
            UpstreamContractError("osrm", "garbage"),
            NoRoute("none"),
        ],
    )
    def test_detours_that_fail_cost_only_an_extra_route(self, failure: Exception) -> None:
        main = route(60, 55)
        service = make_service(StubRouting([main], via=lambda via: failure), StubWeather())

        result = service.plan(request_for(main))

        assert len(result.routes) == 1
        assert "Some alternative routes could not be loaded" in result.notes

    def test_one_detour_failing_still_keeps_the_other(self) -> None:
        main = route(60, 55)

        def via(point: LatLon) -> list[ProviderRoute] | Exception:
            if point.lat > START.lat:
                return UpstreamUnavailable("osrm", "down")
            return [route(64, 50, origin=destination_point(START, SOUTH, 25_000))]

        service = make_service(StubRouting([main], via=via), StubWeather())

        result = service.plan(request_for(main))

        assert len(result.routes) == 2
        assert "Some alternative routes could not be loaded" in result.notes

    def test_a_rejected_detour_request_is_a_bug_and_is_raised(self) -> None:
        main = route(60, 55)
        service = make_service(
            StubRouting([main], via=lambda via: UpstreamError("osrm", "HTTP 400", status=400)),
            StubWeather(),
        )

        with pytest.raises(UpstreamError):
            service.plan(request_for(main))

    def test_a_duplicate_provider_alternative_is_dropped(self) -> None:
        main = route(60, 55)
        twin = route(60, 52)  # same road, a little slower
        service = make_service(StubRouting([main, twin], via=lambda via: []), StubWeather())

        result = service.plan(request_for(main))

        assert len(result.routes) == 1


class TestLoadInTheHeatmap:
    def test_a_heavy_load_raises_the_risk_shown_in_the_heatmap(self) -> None:
        routes = three_routes()
        windy = StubWeather(lambda place: {"wind": 50.0})
        service = make_service(StubRouting(routes), windy)

        light = service.plan(request_for(routes[0], load_lb=20_000)).heatmap.frames[0]
        heavy = service.plan(request_for(routes[0], load_lb=45_000)).heatmap.frames[0]

        assert set(light.risk) == {int(RiskLevel.SEVERE)}
        assert set(heavy.risk) == {int(RiskLevel.NO_TRAVEL)}


class TestRoutingFailures:
    @pytest.mark.parametrize("meters", [800, 1_127, 1_500, 1_609])
    def test_a_trip_under_a_mile_is_refused_before_any_call(self, meters: int) -> None:
        main = route(60, 55)
        routing = StubRouting([main])
        weather = StubWeather()
        close = PlanRequest(
            origin=START,
            destination=destination_point(START, 90.0, meters),
            departure=DEPARTURE,
            load_lb=0,
            interval_mi=25,
        )

        with pytest.raises(TooClose):
            make_service(routing, weather).plan(close)

        assert routing.calls == []
        assert weather.calls == []

    def test_a_trip_just_over_a_mile_is_planned(self) -> None:
        short = route(2, 40)
        service = make_service(StubRouting([short], via=lambda via: []), StubWeather())
        request = PlanRequest(
            origin=short.points[0],
            destination=destination_point(short.points[0], 90.0, 1_700),
            departure=DEPARTURE,
            load_lb=0,
            interval_mi=10,
        )

        assert haversine_m(request.origin, request.destination) > 1_609.344
        assert service.plan(request).routes

    @pytest.mark.parametrize(
        "failure",
        [
            NoRoute("no road"),
            UpstreamUnavailable("osrm", "down"),
            UpstreamTimeout("osrm", "slow"),
            UpstreamContractError("osrm", "garbage"),
            UpstreamError("osrm", "HTTP 400", status=400),
        ],
        ids=["no-route", "unavailable", "timeout", "contract-error", "rejected"],
    )
    def test_a_routing_failure_is_raised_as_its_own_type(self, failure: Exception) -> None:
        main = route(60, 55)
        weather = StubWeather()
        service = make_service(StubRouting([main], outcome=failure), weather)

        with pytest.raises(type(failure)):
            service.plan(request_for(main))

        assert weather.calls == []

    def test_a_snap_distance_over_5_km_is_warned_about(self) -> None:
        main = route(60, 55)
        service = make_service(StubRouting(three_routes(), snap_distance_m=6_200.0), StubWeather())

        result = service.plan(request_for(main))

        assert any("6.2 km from the nearest road" in note for note in result.notes)

    def test_a_snap_distance_just_over_5_km_is_warned_about(self) -> None:
        main = route(60, 55)
        service = make_service(StubRouting(three_routes(), snap_distance_m=5_100.0), StubWeather())

        result = service.plan(request_for(main))

        assert any("5.1 km from the nearest road" in note for note in result.notes)

    @pytest.mark.parametrize("snap_m", [20.0, 5_000.0])
    def test_a_snap_distance_up_to_5_km_is_not(self, snap_m: float) -> None:
        main = route(60, 55)
        service = make_service(StubRouting(three_routes(), snap_distance_m=snap_m), StubWeather())

        result = service.plan(request_for(main))

        assert not any("nearest road" in note for note in result.notes)

    def test_the_snap_distance_of_a_detour_waypoint_is_not_an_origin_warning(self) -> None:
        main = route(60, 55)
        routing = StubRouting([main], via=lambda via: [offset_route(64, 50, NORTH)])
        service = make_service(routing, StubWeather())

        result = service.plan(request_for(main))  # detours report a 9 km snap for their waypoint

        assert not any("nearest road" in note for note in result.notes)


class TestWeatherOutage:
    def test_without_weather_every_level_is_unknown_and_the_plan_still_succeeds(self) -> None:
        routes = three_routes()
        service = make_service(StubRouting(routes), StubWeather(lambda place: None))

        result = service.plan(request_for(routes[0]))

        assert result.banner is PlanBanner.WEATHER_UNAVAILABLE
        for planned in result.routes:
            assert {c.level for c in planned.checkpoints} == {RiskLevel.UNKNOWN}
            assert planned.score.low_confidence
            assert planned.score.avg_risk is None
            assert planned.score.miles_by_level[RiskLevel.LOW] == 0  # never counted as LOW
        assert set(result.heatmap.frames[0].risk) == {-1}

    def test_unknown_is_never_reported_as_safe_in_the_notes_or_the_recommendation(self) -> None:
        routes = three_routes()
        service = make_service(StubRouting(routes), StubWeather(lambda place: None))

        result = service.plan(request_for(routes[0]))

        assert any("Weather is unavailable for" in note for note in result.notes)
        assert result.recommended_route_id is not None  # still ranked, e.g. by time

    def test_part_of_the_weather_missing_marks_only_those_places(self) -> None:
        routes = three_routes()
        weather = StubWeather(lambda place: None if place.lat == 40.0 else {})
        service = make_service(StubRouting(routes), weather)

        result = service.plan(request_for(routes[0]))

        assert result.banner is PlanBanner.WEATHER_UNAVAILABLE
        middle = next(r for r in result.routes if r.label == "Route A")
        other = next(r for r in result.routes if r.label == "Route B")
        assert {c.level for c in middle.checkpoints} == {RiskLevel.UNKNOWN}
        assert {c.level for c in other.checkpoints} == {RiskLevel.LOW}

    def test_one_missing_place_is_worded_in_the_singular(self) -> None:
        routes = three_routes()
        only = routes[0].points[0]
        weather = StubWeather(
            lambda place: (
                None if (place.lat, place.lon) == (round(only.lat, 1), round(only.lon, 1)) else {}
            )
        )
        service = make_service(StubRouting(routes), weather)

        result = service.plan(request_for(routes[0]))

        assert result.banner is PlanBanner.WEATHER_UNAVAILABLE
        assert any(note.startswith("Weather is unavailable for ") for note in result.notes)

    def test_known_danger_outweighs_missing_weather_in_the_banner(self) -> None:
        routes = three_routes()

        def weather_at(place: LatLon) -> dict[str, float] | None:
            if place.lat >= 40.3:  # grid places north of every route: no weather
                return None
            return {"wind": 60.0}  # on the routes: no travel

        weather = StubWeather(weather_at)
        service = make_service(StubRouting(routes), weather)

        result = service.plan(request_for(routes[0]))

        assert result.banner is PlanBanner.NO_SAFE_ROUTE
        assert any("of the weather map" in note for note in result.notes)
        assert result.recommended_route_id is None
        assert result.recommendation_reason is None
        assert len(result.routes) == 3  # still ranked

    def test_a_route_with_no_weather_is_not_ranked_below_one_with_known_danger(self) -> None:
        # SPEC 4.7: unknown miles never count as danger, so with no data a route is not
        # penalised against routes known to have No Travel miles. The banner and the
        # low-confidence flag are what tell the driver.
        routes = three_routes()

        def weather_at(place: LatLon) -> dict[str, float] | None:
            return None if place.lat == 39.8 else {"wind": 60.0}  # the southern route: no data

        service = make_service(StubRouting(routes), StubWeather(weather_at))

        result = service.plan(request_for(routes[0]))

        southern = next(r for r in result.routes if r.label == "Route C")
        assert result.recommended_route_id == southern.id
        assert southern.score.low_confidence
        assert result.banner is PlanBanner.WEATHER_UNAVAILABLE

    def test_no_safe_route_banner_without_any_missing_weather(self) -> None:
        routes = three_routes()
        service = make_service(StubRouting(routes), StubWeather(lambda place: {"wind": 60.0}))

        result = service.plan(request_for(routes[0]))

        assert result.banner is PlanBanner.NO_SAFE_ROUTE
        assert all(r.score.miles_by_level[RiskLevel.NO_TRAVEL] > 0 for r in result.routes)

    def test_stale_weather_is_flagged_in_the_meta_and_the_notes(self) -> None:
        routes = three_routes()
        service = make_service(StubRouting(routes), StubWeather(stale=True))

        result = service.plan(request_for(routes[0]))

        assert result.meta.weather_stale is True
        assert any("may be out of date" in note for note in result.notes)
        assert result.banner is None

    def test_fresh_weather_has_no_stale_note(self) -> None:
        routes = three_routes()
        result = make_service(StubRouting(routes), StubWeather()).plan(request_for(routes[0]))

        assert not any("out of date" in note for note in result.notes)

    def test_a_weather_contract_error_is_not_hidden(self) -> None:
        routes = three_routes()

        class Broken(StubWeather):
            def hourly(self, points, first_day, last_day):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN201
                raise UpstreamContractError("open-meteo", "wrong units")

        with pytest.raises(UpstreamContractError):
            make_service(StubRouting(routes), Broken()).plan(request_for(routes[0]))


class TestNotes:
    def test_the_driving_assumption_comes_first(self) -> None:
        routes = three_routes()
        result = make_service(StubRouting(routes), StubWeather()).plan(request_for(routes[0]))

        assert result.notes[0] == "ETAs assume continuous driving at ≤ 65 mph"

    def test_the_speed_in_the_note_follows_the_setting(self) -> None:
        routes = three_routes()
        service = make_service(StubRouting(routes), StubWeather())
        service._max_speed_mph = 55.0  # noqa: SLF001

        assert service.plan(request_for(routes[0])).notes[0].endswith("55 mph")

    @pytest.mark.parametrize(
        ("load_lb", "warned"), [(80_000, False), (80_001, True), (42_000, False)]
    )
    def test_a_load_above_80000_lb_is_warned_about(self, load_lb: int, warned: bool) -> None:
        routes = three_routes()
        service = make_service(StubRouting(routes), StubWeather())

        result = service.plan(request_for(routes[0], load_lb=load_lb))

        assert any("above 80,000 lb" in note for note in result.notes) is warned


class TestDeadline:
    def test_every_provider_call_runs_inside_the_request_deadline(self) -> None:
        main = route(60, 55)
        routing = StubRouting([main], via=lambda via: [])
        weather = StubWeather()
        clock = FakeClock()

        make_service(routing, weather, clock).plan(request_for(main))

        assert len(routing.deadlines) == 3  # routes, then two detours
        assert all(deadline is not None for deadline in routing.deadlines + weather.deadlines)
        assert weather.deadlines[0].remaining() == pytest.approx(20.0)  # type: ignore[union-attr]

    def test_the_budget_is_shared_by_all_calls(self) -> None:
        main = route(60, 55)
        clock = FakeClock()

        class SlowRouting(StubRouting):
            def routes(self, origin, destination):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN201
                clock.advance(7.0)
                return super().routes(origin, destination)

        weather = StubWeather()
        make_service(SlowRouting([main], via=lambda via: []), weather, clock).plan(
            request_for(main)
        )

        assert weather.deadlines[0].remaining() == pytest.approx(13.0)  # type: ignore[union-attr]

    def test_the_budget_can_be_changed(self) -> None:
        main = route(60, 55)
        weather = StubWeather()
        service = make_service(StubRouting([main], via=lambda via: []), weather, budget_s=5.0)

        service.plan(request_for(main))

        assert weather.deadlines[0].remaining() == pytest.approx(5.0)  # type: ignore[union-attr]

    def test_no_deadline_is_left_behind_after_the_plan(self) -> None:
        main = route(60, 55)
        make_service(StubRouting([main], via=lambda via: []), StubWeather()).plan(request_for(main))

        assert current_deadline() is None


class TestRequestInvariants:
    def base(self, **changes: object) -> dict[str, object]:
        values: dict[str, object] = {
            "origin": START,
            "destination": destination_point(START, 90.0, 50_000),
            "departure": DEPARTURE,
            "load_lb": 20_000,
            "interval_mi": 25,
        }
        values.update(changes)
        return values

    def test_a_valid_request(self) -> None:
        request = PlanRequest(**self.base())  # type: ignore[arg-type]

        assert request.interval_mi == 25

    @pytest.mark.parametrize(
        ("changes", "message"),
        [
            ({"departure": datetime(2026, 10, 18, 14, 0)}, "timezone-aware"),  # noqa: DTZ001
            ({"load_lb": -1}, "negative"),
            ({"interval_mi": 5}, "interval"),
            ({"interval_mi": 30}, "interval"),
        ],
    )
    def test_invalid_requests_are_refused(self, changes: dict[str, object], message: str) -> None:
        with pytest.raises(ValueError, match=message):
            PlanRequest(**self.base(**changes))  # type: ignore[arg-type]

    @pytest.mark.parametrize("interval", [10, 25, 50])
    def test_the_three_intervals_are_accepted(self, interval: int) -> None:
        assert PlanRequest(**self.base(interval_mi=interval)).interval_mi == interval  # type: ignore[arg-type]

    def test_the_departure_may_be_in_any_offset(self) -> None:
        offset = datetime(2026, 10, 18, 8, 0, tzinfo=timezone(timedelta(hours=-6)))

        assert PlanRequest(**self.base(departure=offset)).departure == DEPARTURE.replace(tzinfo=UTC)  # type: ignore[arg-type]
