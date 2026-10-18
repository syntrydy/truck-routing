"""The plan service through the real OSRM and Open-Meteo adapters, on recorded responses."""

import copy
import json
import uuid
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from django.core.cache.backends.locmem import LocMemCache

from planner.domain.models import LatLon, RiskLevel
from planner.domain.risk import WindBasis
from planner.infra.errors import UpstreamUnavailable
from planner.infra.http import ProviderPolicy, UpstreamClient
from planner.providers.protocols import NoRoute
from planner.services.container import Container, build_container
from planner.services.models import PlanBanner, PlanRequest
from tests.infra.fakes import FakeClock, FixedJitter

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
OSRM = "router.project-osrm.org"
OPEN_METEO = "api.open-meteo.com"
NWS = "api.weather.gov"
BOULDER = LatLon(40.0150, -105.2705)
FORT_COLLINS = LatLon(40.5853, -105.0844)
DEPARTURE = datetime(2026, 10, 18, 14, 0, tzinfo=UTC)


def fixture(path: str) -> Any:  # noqa: ANN401
    return json.loads((FIXTURES / path).read_text())


class Network:
    """The recorded OSRM and Open-Meteo replies, and a count of the calls made."""

    def __init__(
        self, *, osrm_up: bool = True, weather_up: bool = True, nws_up: bool | None = None
    ) -> None:
        self.osrm_up = osrm_up
        self.weather_up = weather_up
        self.nws_up = weather_up if nws_up is None else nws_up  # both fail together by default
        self.nws_calls = 0
        self.osrm_calls: list[int] = []  # waypoints per call
        self.weather_calls: list[int] = []  # places per call
        self._place = fixture("openmeteo/single_point.json")

    def osrm(self, request: httpx.Request) -> httpx.Response:
        waypoints = request.url.path.rsplit("/", 1)[-1].count(";") + 1
        self.osrm_calls.append(waypoints)
        if not self.osrm_up:
            return httpx.Response(503)
        if waypoints > 2:  # a detour through a via point: the demo server had none to offer
            return httpx.Response(400, json=fixture("osrm/no_route.json"))
        return httpx.Response(200, json=fixture("osrm/two_routes.json"))

    def nws(self, request: httpx.Request) -> httpx.Response:
        self.nws_calls += 1
        if not self.nws_up:
            return httpx.Response(503)
        if request.url.path.startswith("/points/"):
            return httpx.Response(200, json=fixture("nws/points_boulder.json"))
        return httpx.Response(200, json=fixture("nws/gridpoints_boulder.json"))

    def open_meteo(self, request: httpx.Request) -> httpx.Response:
        count = len(request.url.params["latitude"].split(","))
        self.weather_calls.append(count)
        if not self.weather_up:
            return httpx.Response(503)
        places = [copy.deepcopy(self._place) for _ in range(count)]
        return httpx.Response(200, json=places if count > 1 else places[0])


@pytest.fixture
def container_and_clock() -> Iterator[tuple[Container, FakeClock]]:
    clock = FakeClock()
    client = UpstreamClient(
        [
            ProviderPolicy("osrm", timeout_s=8.0, max_concurrency=1),
            ProviderPolicy("open-meteo", timeout_s=10.0, max_concurrency=4),
            ProviderPolicy("nws", timeout_s=8.0, max_concurrency=12),
        ],
        [OSRM, OPEN_METEO, NWS],
        "tests/1.0",
        clock=clock,
        sleep=clock.sleep,
        jitter=FixedJitter(0.0),
    )
    backend = LocMemCache(f"e2e-{uuid.uuid4()}", {})
    yield (
        build_container(
            client=client,
            cache_backend=backend,
            ors_api_key="",
            max_speed_mph=65.0,
            wind_basis=WindBasis.SUSTAINED,
        ),
        clock,
    )
    backend.clear()


def run(network: Network, container: Container, **changes: Any) -> Any:  # noqa: ANN401
    request = PlanRequest(
        origin=BOULDER,
        destination=FORT_COLLINS,
        departure=DEPARTURE,
        load_lb=20_000,
        interval_mi=10,
    )
    with respx.mock(assert_all_called=False) as router:
        router.get(host=OSRM).mock(side_effect=network.osrm)
        router.get(host=OPEN_METEO).mock(side_effect=network.open_meteo)
        router.get(host=NWS).mock(side_effect=network.nws)
        return container.plan_service.plan(replace(request, **changes))


class TestRecordedTrip:
    def test_a_complete_plan_comes_back(
        self, container_and_clock: tuple[Container, FakeClock]
    ) -> None:
        container, _ = container_and_clock
        network = Network()

        result = run(network, container)

        assert len(result.routes) == 2
        assert [r.rank for r in result.routes] == [1, 2]
        assert result.recommended_route_id == result.routes[0].id
        assert result.banner is None
        assert result.meta.routing_source == "osrm"
        assert result.meta.weather_source == "open-meteo"
        assert result.meta.weather_stale is False

    def test_the_two_recorded_routes_become_two_ranked_routes(
        self, container_and_clock: tuple[Container, FakeClock]
    ) -> None:
        container, _ = container_and_clock
        recorded = fixture("osrm/two_routes.json")

        result = run(Network(), container)

        by_duration = sorted(result.routes, key=lambda r: r.duration_s)
        assert by_duration[0].distance_mi == pytest.approx(
            recorded["routes"][0]["distance"] / 1609.344, rel=0.02
        )
        for route in result.routes:
            assert route.checkpoints[0].eta == DEPARTURE
            assert route.checkpoints[-1].distance_mi == pytest.approx(route.distance_mi)

    def test_the_recorded_weather_is_used_at_every_checkpoint(
        self, container_and_clock: tuple[Container, FakeClock]
    ) -> None:
        container, _ = container_and_clock
        recorded = fixture("openmeteo/single_point.json")["hourly"]["wind_speed_10m"]

        result = run(Network(), container)

        for route in result.routes:
            for checkpoint in route.checkpoints:
                assert checkpoint.weather is not None
                assert checkpoint.weather.wind_mph is not None
                assert min(recorded) <= checkpoint.weather.wind_mph <= max(recorded)
                assert checkpoint.level is RiskLevel.LOW  # a calm, dry day in the recording

    def test_the_heatmap_has_49_frames_over_the_corridor(
        self, container_and_clock: tuple[Container, FakeClock]
    ) -> None:
        container, _ = container_and_clock

        result = run(Network(), container)

        heatmap = result.heatmap
        assert heatmap.start == DEPARTURE
        assert len(heatmap.frames) == 49
        assert 20 <= len(heatmap.points) <= 200
        assert all(len(frame.risk) == len(heatmap.points) for frame in heatmap.frames)
        assert set(heatmap.frames[0].risk) == {0}

    def test_the_notes_say_what_happened(
        self, container_and_clock: tuple[Container, FakeClock]
    ) -> None:
        container, _ = container_and_clock

        result = run(Network(), container)

        assert result.notes == (
            "ETAs assume continuous driving at ≤ 65 mph",
            "Only 2 distinct routes exist for this trip",
            "Some alternative routes could not be loaded",
        )

    def test_detours_were_asked_for_once_per_side_after_the_main_request(
        self, container_and_clock: tuple[Container, FakeClock]
    ) -> None:
        container, _ = container_and_clock
        network = Network()

        run(network, container)

        assert network.osrm_calls == [2, 3, 3]

    def test_the_weather_is_fetched_in_batches_of_at_most_100_places(
        self, container_and_clock: tuple[Container, FakeClock]
    ) -> None:
        container, _ = container_and_clock
        network = Network()

        run(network, container)

        assert network.weather_calls
        assert all(count <= 100 for count in network.weather_calls)

    def test_a_second_plan_reuses_the_cached_weather(
        self, container_and_clock: tuple[Container, FakeClock]
    ) -> None:
        container, _ = container_and_clock
        network = Network()
        run(network, container)
        calls_after_first = len(network.weather_calls)

        run(network, container)

        assert len(network.weather_calls) == calls_after_first


class TestOutages:
    def test_a_weather_outage_gives_unknown_levels_and_a_banner_not_an_error(
        self, container_and_clock: tuple[Container, FakeClock]
    ) -> None:
        container, _ = container_and_clock

        result = run(Network(weather_up=False), container)

        assert result.banner is PlanBanner.WEATHER_UNAVAILABLE
        assert result.routes
        for route in result.routes:
            assert {c.level for c in route.checkpoints} == {RiskLevel.UNKNOWN}
            assert route.score.low_confidence
        assert set(result.heatmap.frames[0].risk) == {-1}

    def test_when_open_meteo_is_down_the_nws_supplies_the_weather(
        self, container_and_clock: tuple[Container, FakeClock]
    ) -> None:
        container, _ = container_and_clock
        network = Network(weather_up=False, nws_up=True)

        result = run(network, container)

        assert result.banner is None
        assert result.meta.weather_source == "nws"
        for route in result.routes:
            assert {c.level for c in route.checkpoints} == {RiskLevel.LOW}
            assert not route.score.low_confidence
        assert network.nws_calls > 0

    def test_open_meteo_working_means_the_nws_is_never_asked(
        self, container_and_clock: tuple[Container, FakeClock]
    ) -> None:
        container, _ = container_and_clock
        network = Network()

        result = run(network, container)

        assert result.meta.weather_source == "open-meteo"
        assert network.nws_calls == 0

    def test_a_routing_outage_is_a_typed_error_and_no_weather_is_fetched(
        self, container_and_clock: tuple[Container, FakeClock]
    ) -> None:
        container, _ = container_and_clock
        network = Network(osrm_up=False)

        with pytest.raises(UpstreamUnavailable):
            run(network, container)

        assert network.weather_calls == []

    def test_no_route_is_raised_as_no_route(
        self, container_and_clock: tuple[Container, FakeClock]
    ) -> None:
        container, _ = container_and_clock

        class NoRouteNetwork(Network):
            def osrm(self, request: httpx.Request) -> httpx.Response:
                return httpx.Response(400, json=fixture("osrm/no_route.json"))

        with pytest.raises(NoRoute):
            run(NoRouteNetwork(), container)
