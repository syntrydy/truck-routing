import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from planner.domain.geometry import haversine_m
from planner.domain.models import LatLon
from planner.infra.errors import UpstreamContractError, UpstreamError, UpstreamUnavailable
from planner.infra.http import ProviderPolicy, UpstreamClient
from planner.providers.protocols import NoRoute, RoutingProvider
from planner.providers.routing_ors import OrsRoutingProvider
from tests.infra.fakes import FakeClock, FixedJitter

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ors"
HOST = "api.openrouteservice.org"
URL = f"https://{HOST}/v2/directions/driving-hgv/geojson"
KEY = "NOT-A-REAL-CREDENTIAL-5678"
BOULDER = LatLon(40.0150, -105.2705)
FORT_COLLINS = LatLon(40.5853, -105.0844)
DENVER = LatLon(39.7392, -104.9903)
WAYPOINT = LatLon(39.95, -105.05)


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text())  # type: ignore[no-any-return]


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def make_provider(clock: FakeClock, **kwargs: Any) -> OrsRoutingProvider:
    client = UpstreamClient(
        [ProviderPolicy("openrouteservice", timeout_s=8.0, max_concurrency=1)],
        [HOST],
        "tests/1.0",
        clock=clock,
        sleep=clock.sleep,
        jitter=FixedJitter(1.0),
    )
    return OrsRoutingProvider(client, KEY, **kwargs)


def respond(api: respx.MockRouter, body: Any) -> respx.Route:
    return api.post(host=HOST).respond(200, json=body)


class TestRoute:
    def test_maps_the_route(self, api: respx.MockRouter, clock: FakeClock) -> None:
        body = fixture("one_route")
        respond(api, body)

        result = make_provider(clock).routes(BOULDER, FORT_COLLINS)

        assert result.source == "openrouteservice"
        assert len(result.routes) == 1
        route = result.routes[0]
        summary = body["features"][0]["properties"]["summary"]
        assert (route.distance_m, route.duration_s) == (summary["distance"], summary["duration"])
        assert len(route.points) == len(body["features"][0]["geometry"]["coordinates"])
        lon, lat = body["features"][0]["geometry"]["coordinates"][0]
        assert route.points[0] == LatLon(lat, lon)

    def test_segment_times_are_derived_from_the_steps(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        body = fixture("one_route")
        respond(api, body)

        route = make_provider(clock).routes(BOULDER, FORT_COLLINS).routes[0]

        steps = body["features"][0]["properties"]["segments"][0]["steps"]
        assert len(route.segment_durations_s) == len(route.points) - 1
        assert len(route.segment_distances_m) == len(route.points) - 1
        for step in steps:
            first, last = step["way_points"]
            assert sum(route.segment_durations_s[first:last]) == pytest.approx(step["duration"])
            assert sum(route.segment_distances_m[first:last]) == pytest.approx(step["distance"])
        assert sum(route.segment_durations_s) == pytest.approx(route.duration_s, rel=1e-3)

    def test_a_steps_time_is_spread_in_proportion_to_segment_length(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        body = fixture("one_route")
        respond(api, body)

        route = make_provider(clock).routes(BOULDER, FORT_COLLINS).routes[0]

        first, last = body["features"][0]["properties"]["segments"][0]["steps"][0]["way_points"]
        speeds = [
            haversine_m(route.points[i], route.points[i + 1]) / route.segment_durations_s[i]
            for i in range(first, last)
            if route.segment_durations_s[i] > 0
        ]
        assert max(speeds) == pytest.approx(min(speeds))

    def test_a_step_over_zero_length_segments_is_split_evenly(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        body = fixture("one_route")
        coordinates = body["features"][0]["geometry"]["coordinates"]
        first, last = body["features"][0]["properties"]["segments"][0]["steps"][0]["way_points"]
        coordinates[first : last + 1] = [coordinates[first]] * (last - first + 1)
        respond(api, body)

        route = make_provider(clock).routes(BOULDER, FORT_COLLINS).routes[0]

        durations = route.segment_durations_s[first:last]
        assert durations == pytest.approx([durations[0]] * len(durations))
        assert sum(durations) > 0

    def test_snap_distance_compares_the_requested_points_with_the_route_ends(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        body = fixture("one_route")
        respond(api, body)

        result = make_provider(clock).routes(BOULDER, FORT_COLLINS)

        points = result.routes[0].points
        expected = max(haversine_m(BOULDER, points[0]), haversine_m(FORT_COLLINS, points[-1]))
        assert result.snap_distance_m == pytest.approx(expected)

    def test_it_satisfies_the_routing_provider_protocol(self, clock: FakeClock) -> None:
        provider: RoutingProvider = make_provider(clock)

        assert provider.name == "openrouteservice"


class TestRequest:
    def test_posts_lon_lat_coordinates_for_the_truck_profile(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = respond(api, fixture("one_route"))

        make_provider(clock).routes(BOULDER, FORT_COLLINS)

        request = route.calls.last.request
        assert request.method == "POST"
        assert request.url.path == "/v2/directions/driving-hgv/geojson"
        assert json.loads(request.content) == {
            "coordinates": [[-105.2705, 40.015], [-105.0844, 40.5853]],
            "instructions": True,
        }

    def test_the_key_goes_in_a_header_and_never_in_the_url(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = respond(api, fixture("one_route"))

        make_provider(clock).routes(BOULDER, FORT_COLLINS)

        request = route.calls.last.request
        assert request.headers["Authorization"] == KEY
        assert KEY not in str(request.url)
        assert KEY not in request.content.decode()

    def test_a_trailing_slash_in_the_base_url_is_ignored(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = respond(api, fixture("one_route"))

        make_provider(clock, base_url=f"https://{HOST}/").routes(BOULDER, FORT_COLLINS)

        assert route.calls.last.request.url.path == "/v2/directions/driving-hgv/geojson"

    def test_an_api_key_is_required(self, clock: FakeClock) -> None:
        with pytest.raises(ValueError, match="API key"):
            OrsRoutingProvider(
                UpstreamClient([], [HOST], "tests/1.0", clock=clock, sleep=clock.sleep), ""
            )

    def test_the_key_is_not_shown_by_repr(self, clock: FakeClock) -> None:
        provider = make_provider(clock)

        assert KEY not in repr(provider)
        assert KEY not in str(provider)


class TestRouteVia:
    def test_requests_three_points_and_maps_the_waypoint_snap(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        body = fixture("via_waypoint")
        route = respond(api, body)

        result = make_provider(clock).route_via(DENVER, WAYPOINT, BOULDER)

        assert len(json.loads(route.calls.last.request.content)["coordinates"]) == 3
        points = result.routes[0].points
        wanted = [DENVER, WAYPOINT, BOULDER]
        indices = body["features"][0]["properties"]["way_points"]
        assert result.snap_distance_m == pytest.approx(
            max(haversine_m(w, points[i]) for w, i in zip(wanted, indices, strict=True))
        )
        assert len(result.routes[0].segment_durations_s) == len(points) - 1


class TestNoRoute:
    @pytest.mark.parametrize("name", ["route_not_found", "point_not_found"])
    def test_the_documented_codes_mean_no_route(
        self, api: respx.MockRouter, clock: FakeClock, name: str
    ) -> None:
        body = fixture(name)
        api.post(host=HOST).respond(404, json=body)

        with pytest.raises(NoRoute, match=body["error"]["message"]):
            make_provider(clock).routes(BOULDER, FORT_COLLINS)

    def test_the_code_may_be_a_string(self, api: respx.MockRouter, clock: FakeClock) -> None:
        api.post(host=HOST).respond(404, json={"error": {"code": "2009", "message": "none"}})

        with pytest.raises(NoRoute, match="none"):
            make_provider(clock).routes(BOULDER, FORT_COLLINS)

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(400, json={"error": {"code": 2004, "message": "too long"}}),
            httpx.Response(403, json={"error": {"code": 2003, "message": "bad key"}}),
            httpx.Response(404, json={"error": "plain text error"}),
            httpx.Response(404, json={"error": {"code": True}}),
            httpx.Response(404, json={"error": {"message": "no code"}}),
            httpx.Response(404, json=["2009"]),
            httpx.Response(404, text="not json"),
            httpx.Response(404),
        ],
        ids=[
            "limit",
            "forbidden",
            "text-error",
            "bool-code",
            "no-code",
            "not-object",
            "not-json",
            "empty-body",
        ],
    )
    def test_other_rejections_stay_upstream_errors(
        self, api: respx.MockRouter, clock: FakeClock, response: httpx.Response
    ) -> None:
        api.post(host=HOST).mock(return_value=response)

        with pytest.raises(UpstreamError) as raised:
            make_provider(clock).routes(BOULDER, FORT_COLLINS)

        assert type(raised.value) is UpstreamError

    def test_a_rate_limit_is_an_outage_not_a_rejection(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        api.post(host=HOST).respond(429)

        with pytest.raises(UpstreamUnavailable):
            make_provider(clock).routes(BOULDER, FORT_COLLINS)


def edit(change: Any) -> dict[str, Any]:
    """The one-route fixture, modified in place by ``change(feature)``."""
    body = fixture("one_route")
    change(body["features"][0])
    return body


def steps_of(feature: dict[str, Any]) -> list[dict[str, Any]]:
    return feature["properties"]["segments"][0]["steps"]  # type: ignore[no-any-return]


def drop_step(feature: dict[str, Any]) -> None:
    del steps_of(feature)[1]


def reverse_step(feature: dict[str, Any]) -> None:
    steps_of(feature)[0]["way_points"] = [14, 0]


def reversed_inside_a_chain(feature: dict[str, Any]) -> None:
    """Steps 0-28, 28-14, 14-42 still chain end to start, but the middle one runs backwards."""
    steps = steps_of(feature)
    middle, tail = steps[1], steps[2]
    steps[0]["way_points"] = [0, 28]
    middle["way_points"] = [28, 14]
    tail["way_points"] = [14, 42]


def set_step(key: str, value: Any) -> Any:
    def change(feature: dict[str, Any]) -> None:
        steps_of(feature)[0][key] = value

    return change


def set_prop(key: str, value: Any) -> Any:
    def change(feature: dict[str, Any]) -> None:
        if value is None:
            del feature["properties"][key]
        else:
            feature["properties"][key] = value

    return change


MALFORMED: dict[str, Any] = {
    "array": [],
    "no-features": {"type": "FeatureCollection"},
    "empty-features": {"features": []},
    "features-not-a-list": {"features": {}},
    "feature-not-an-object": {"features": [3]},
    "no-geometry": edit(lambda f: f.pop("geometry")),
    "point-geometry": edit(lambda f: f["geometry"].update(type="Point")),
    "one-coordinate": edit(lambda f: f["geometry"].update(coordinates=[[-105.0, 40.0]])),
    "text-coordinate": edit(lambda f: f["geometry"].update(coordinates=[["x", 1.0], [2.0, 3.0]])),
    "no-properties": edit(lambda f: f.pop("properties")),
    "no-summary": edit(set_prop("summary", None)),
    "text-distance": edit(set_prop("summary", {"distance": "far", "duration": 1.0})),
    "negative-duration": edit(set_prop("summary", {"distance": 1.0, "duration": -1.0})),
    "no-segments": edit(set_prop("segments", None)),
    "segment-not-an-object": edit(set_prop("segments", [1])),
    "segment-without-steps": edit(set_prop("segments", [{}])),
    "no-steps-at-all": edit(set_prop("segments", [{"steps": []}])),
    "step-not-an-object": edit(set_prop("segments", [{"steps": [1]}])),
    "step-gap": edit(drop_step),
    "step-reversed": edit(reverse_step),
    "step-reversed-inside-a-chain": edit(reversed_inside_a_chain),
    "step-text-index": edit(set_step("way_points", ["a", "b"])),
    "step-boolean-index": edit(set_step("way_points", [True, 14])),
    "step-index-beyond-geometry": edit(set_step("way_points", [0, 9999])),
    "step-three-indices": edit(set_step("way_points", [0, 7, 14])),
    "step-starts-late": edit(set_step("way_points", [1, 14])),
    "step-negative-duration": edit(set_step("duration", -5.0)),
    "step-text-distance": edit(set_step("distance", "x")),
    "no-way-points": edit(set_prop("way_points", None)),
    "way-points-too-few": edit(set_prop("way_points", [0])),
    "way-points-out-of-order": edit(set_prop("way_points", [42, 0])),
    "way-points-out-of-range": edit(set_prop("way_points", [0, 9999])),
}


class TestMalformedResponses:
    @pytest.mark.parametrize("body", list(MALFORMED.values()), ids=list(MALFORMED))
    def test_unusable_bodies_are_contract_errors(
        self, api: respx.MockRouter, clock: FakeClock, body: Any
    ) -> None:
        respond(api, copy.deepcopy(body))

        with pytest.raises(UpstreamContractError):
            make_provider(clock).routes(BOULDER, FORT_COLLINS)

    def test_a_step_without_length_may_not_carry_time(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        body = edit(lambda f: steps_of(f)[-1].update(duration=30.0))
        respond(api, body)

        with pytest.raises(UpstreamContractError, match="without length"):
            make_provider(clock).routes(BOULDER, FORT_COLLINS)

    def test_a_reply_that_is_not_json(self, api: respx.MockRouter, clock: FakeClock) -> None:
        api.post(host=HOST).respond(200, text="<html>")

        with pytest.raises(UpstreamContractError):
            make_provider(clock).routes(BOULDER, FORT_COLLINS)

    def test_the_error_names_the_provider_and_not_the_key(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        respond(api, {"features": []})

        with pytest.raises(UpstreamContractError) as raised:
            make_provider(clock).routes(BOULDER, FORT_COLLINS)

        assert raised.value.provider == "openrouteservice"
        assert KEY not in str(raised.value)
