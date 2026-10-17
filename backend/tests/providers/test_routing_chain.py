import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from planner.domain.models import LatLon
from planner.infra.errors import (
    HostNotAllowed,
    UpstreamContractError,
    UpstreamError,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from planner.infra.http import ProviderPolicy, UpstreamClient
from planner.providers.protocols import NoRoute, ProviderRoute, RoutingProvider, RoutingResult
from planner.providers.routing_chain import FallbackRoutingProvider, build_routing_provider
from planner.providers.routing_ors import OrsRoutingProvider
from planner.providers.routing_osrm import OsrmRoutingProvider
from tests.infra.fakes import FakeClock, FixedJitter

ORIGIN = LatLon(40.0150, -105.2705)
DESTINATION = LatLon(40.5853, -105.0844)
VIA = LatLon(40.3, -105.2)
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def result_from(source: str) -> RoutingResult:
    route = ProviderRoute(
        points=(ORIGIN, DESTINATION),
        distance_m=1.0,
        duration_s=1.0,
        segment_durations_s=(1.0,),
        segment_distances_m=(1.0,),
    )
    return RoutingResult(routes=(route,), snap_distance_m=0.0, source=source)


class Stub:
    """A provider that returns a result or raises, and records how it was called."""

    def __init__(self, name: str, outcome: RoutingResult | Exception) -> None:
        self.name = name
        self.outcome = outcome
        self.calls: list[str] = []

    def routes(self, origin: LatLon, destination: LatLon) -> RoutingResult:
        self.calls.append("routes")
        return self._answer()

    def route_via(self, origin: LatLon, via: LatLon, destination: LatLon) -> RoutingResult:
        self.calls.append("route_via")
        return self._answer()

    def _answer(self) -> RoutingResult:
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def chain(*providers: Stub) -> FallbackRoutingProvider:
    return FallbackRoutingProvider(list(providers))


class TestFallThrough:
    def test_the_first_provider_answers(self) -> None:
        first, second = Stub("osrm", result_from("osrm")), Stub("ors", result_from("ors"))

        result = chain(first, second).routes(ORIGIN, DESTINATION)

        assert result.source == "osrm"
        assert second.calls == []

    @pytest.mark.parametrize(
        "failure",
        [
            UpstreamUnavailable("osrm", "down"),
            UpstreamTimeout("osrm", "slow"),
            UpstreamContractError("osrm", "garbage"),
        ],
        ids=["unavailable", "timeout", "contract-error"],
    )
    def test_the_next_provider_answers_when_the_first_fails(self, failure: Exception) -> None:
        first, second = Stub("osrm", failure), Stub("ors", result_from("ors"))

        result = chain(first, second).routes(ORIGIN, DESTINATION)

        assert result.source == "ors"  # meta.routing_source follows the provider that answered
        assert first.calls == ["routes"]
        assert second.calls == ["routes"]

    def test_route_via_falls_through_the_same_way(self) -> None:
        first = Stub("osrm", UpstreamUnavailable("osrm", "down"))
        second = Stub("ors", result_from("ors"))

        result = chain(first, second).route_via(ORIGIN, VIA, DESTINATION)

        assert result.source == "ors"
        assert (first.calls, second.calls) == (["route_via"], ["route_via"])

    def test_the_providers_are_tried_in_order(self) -> None:
        stubs = [
            Stub("a", UpstreamUnavailable("a", "down")),
            Stub("b", UpstreamTimeout("b", "slow")),
            Stub("c", result_from("c")),
        ]

        assert chain(*stubs).routes(ORIGIN, DESTINATION).source == "c"

    def test_when_every_provider_fails_the_last_failure_is_raised(self) -> None:
        first = Stub("osrm", UpstreamUnavailable("osrm", "down"))
        second = Stub("ors", UpstreamTimeout("ors", "slow"))

        with pytest.raises(UpstreamTimeout, match="ors"):
            chain(first, second).routes(ORIGIN, DESTINATION)

        assert first.calls == second.calls == ["routes"]


class TestNoFallThrough:
    def test_no_route_is_an_answer_and_is_passed_on(self) -> None:
        first, second = Stub("osrm", NoRoute("no road")), Stub("ors", result_from("ors"))

        with pytest.raises(NoRoute, match="no road"):
            chain(first, second).routes(ORIGIN, DESTINATION)

        assert second.calls == []

    def test_a_rejected_request_is_passed_on(self) -> None:
        first = Stub("osrm", UpstreamError("osrm", "HTTP 400", status=400))
        second = Stub("ors", result_from("ors"))

        with pytest.raises(UpstreamError) as raised:
            chain(first, second).routes(ORIGIN, DESTINATION)

        assert type(raised.value) is UpstreamError
        assert second.calls == []

    def test_programming_errors_are_not_hidden(self) -> None:
        first = Stub("osrm", HostNotAllowed("host"))
        second = Stub("ors", result_from("ors"))

        with pytest.raises(HostNotAllowed):
            chain(first, second).routes(ORIGIN, DESTINATION)

        assert second.calls == []


def test_a_chain_needs_at_least_one_provider() -> None:
    with pytest.raises(ValueError, match="at least one"):
        FallbackRoutingProvider([])


def test_a_chain_is_itself_a_routing_provider() -> None:
    provider: RoutingProvider = chain(Stub("osrm", result_from("osrm")))

    assert provider.name == "fallback"


OSRM_HOST = "router.project-osrm.org"
ORS_HOST = "api.openrouteservice.org"


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


def real_client(clock: FakeClock) -> UpstreamClient:
    return UpstreamClient(
        [
            ProviderPolicy("osrm", timeout_s=8.0, max_concurrency=1),
            ProviderPolicy("openrouteservice", timeout_s=8.0, max_concurrency=1),
        ],
        [OSRM_HOST, ORS_HOST],
        "tests/1.0",
        clock=clock,
        sleep=clock.sleep,
        jitter=FixedJitter(1.0),
    )


def fixture(path: str) -> dict[str, Any]:
    return json.loads((FIXTURES / path).read_text())  # type: ignore[no-any-return]


class TestBuildRoutingProvider:
    def test_without_a_key_it_is_osrm_alone(self) -> None:
        provider = build_routing_provider(real_client(FakeClock()), "")

        assert isinstance(provider, OsrmRoutingProvider)

    def test_with_a_key_it_is_a_chain_of_osrm_then_openrouteservice(self) -> None:
        provider = build_routing_provider(real_client(FakeClock()), "a-key")

        assert isinstance(provider, FallbackRoutingProvider)
        assert [type(p) for p in provider._providers] == [  # noqa: SLF001
            OsrmRoutingProvider,
            OrsRoutingProvider,
        ]

    def test_openrouteservice_answers_when_osrm_is_down(self, api: respx.MockRouter) -> None:
        clock = FakeClock()
        osrm = api.get(host=OSRM_HOST).respond(503)
        ors = api.post(host=ORS_HOST).respond(200, json=fixture("ors/one_route.json"))
        provider = build_routing_provider(real_client(clock), "a-key")

        result = provider.routes(ORIGIN, DESTINATION)

        assert result.source == "openrouteservice"
        assert osrm.call_count == 2  # one try and its retry
        assert ors.call_count == 1

    def test_osrm_answers_first_when_it_is_up(self, api: respx.MockRouter) -> None:
        clock = FakeClock()
        api.get(host=OSRM_HOST).respond(200, json=fixture("osrm/two_routes.json"))
        ors = api.post(host=ORS_HOST).respond(200, json=fixture("ors/one_route.json"))
        provider = build_routing_provider(real_client(clock), "a-key")

        assert provider.routes(ORIGIN, DESTINATION).source == "osrm"
        assert not ors.called

    def test_without_a_key_an_osrm_outage_is_an_error(self, api: respx.MockRouter) -> None:
        clock = FakeClock()
        api.get(host=OSRM_HOST).respond(503)
        ors = api.post(host=ORS_HOST).respond(200, json=fixture("ors/one_route.json"))

        with pytest.raises(UpstreamUnavailable):
            build_routing_provider(real_client(clock), "").routes(ORIGIN, DESTINATION)

        assert not ors.called

    def test_an_open_osrm_breaker_goes_straight_to_openrouteservice(
        self, api: respx.MockRouter
    ) -> None:
        clock = FakeClock()
        osrm = api.get(host=OSRM_HOST).respond(503)
        api.post(host=ORS_HOST).respond(200, json=fixture("ors/one_route.json"))
        provider = build_routing_provider(real_client(clock), "a-key")
        for _ in range(3):
            provider.routes(ORIGIN, DESTINATION)
        calls_before = osrm.call_count

        result = provider.routes(ORIGIN, DESTINATION)

        assert result.source == "openrouteservice"
        assert osrm.call_count == calls_before

    def test_no_route_from_osrm_is_not_retried_on_openrouteservice(
        self, api: respx.MockRouter
    ) -> None:
        clock = FakeClock()
        api.get(host=OSRM_HOST).mock(
            return_value=httpx.Response(400, json=fixture("osrm/no_route.json"))
        )
        ors = api.post(host=ORS_HOST).respond(200, json=fixture("ors/one_route.json"))

        with pytest.raises(NoRoute):
            build_routing_provider(real_client(clock), "a-key").routes(ORIGIN, DESTINATION)

        assert not ors.called
