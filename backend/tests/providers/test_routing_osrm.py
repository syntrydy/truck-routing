import copy
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
from planner.infra.resilience import MinSpacing
from planner.providers.protocols import NoRoute, RoutingProvider
from planner.providers.routing_osrm import OsrmRoutingProvider
from tests.infra.fakes import FakeClock, FixedJitter

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "osrm"
HOST = "router.project-osrm.org"
BOULDER = LatLon(40.0150, -105.2705)
FORT_COLLINS = LatLon(40.5853, -105.0844)
DENVER = LatLon(39.7392, -104.9903)
COLORADO_SPRINGS = LatLon(38.8339, -104.8214)
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


def make_provider(clock: FakeClock, **kwargs: object) -> OsrmRoutingProvider:
    client = UpstreamClient(
        [ProviderPolicy("osrm", timeout_s=8.0, max_concurrency=1)],
        [HOST],
        "tests/1.0",
        clock=clock,
        sleep=clock.sleep,
        jitter=FixedJitter(1.0),
        gates=kwargs.pop("gates", None),  # type: ignore[arg-type]
    )
    return OsrmRoutingProvider(client, **kwargs)  # type: ignore[arg-type]


def mock_ok(api: respx.MockRouter, body: dict[str, Any]) -> respx.Route:
    return api.get(host=HOST).respond(200, json=body)


class TestRoutes:
    def test_maps_the_alternatives_in_the_order_the_server_gives_them(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        body = fixture("two_routes")
        mock_ok(api, body)

        result = make_provider(clock).routes(BOULDER, FORT_COLLINS)

        assert result.source == "osrm"
        assert len(result.routes) == 2
        first, second = result.routes
        assert first.duration_s == body["routes"][0]["duration"]
        assert second.duration_s == body["routes"][1]["duration"]
        assert first.duration_s <= second.duration_s

    def test_maps_geometry_totals_and_per_segment_annotations(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        body = fixture("two_routes")
        mock_ok(api, body)

        route = make_provider(clock).routes(BOULDER, FORT_COLLINS).routes[0]
        raw = body["routes"][0]

        assert len(route.points) == len(raw["geometry"]["coordinates"])
        lon, lat = raw["geometry"]["coordinates"][0]
        assert route.points[0] == LatLon(lat, lon)  # GeoJSON is [lon, lat]
        assert route.distance_m == raw["distance"]
        assert len(route.segment_durations_s) == len(route.points) - 1
        assert len(route.segment_distances_m) == len(route.points) - 1
        assert sum(route.segment_distances_m) == pytest.approx(route.distance_m, rel=0.01)
        # Real OSRM data: the per-segment times leave out the turn and signal penalties that
        # the route total includes, so they add up to somewhat less (about 3% here).
        assert sum(route.segment_durations_s) < route.duration_s
        assert sum(route.segment_durations_s) == pytest.approx(route.duration_s, rel=0.10)

    def test_the_route_runs_from_near_the_origin_to_near_the_destination(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        mock_ok(api, fixture("two_routes"))

        route = make_provider(clock).routes(BOULDER, FORT_COLLINS).routes[0]

        assert route.points[0].lat == pytest.approx(BOULDER.lat, abs=0.01)
        assert route.points[-1].lon == pytest.approx(FORT_COLLINS.lon, abs=0.01)

    def test_the_snap_distance_is_the_largest_waypoint_distance(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        body = fixture("two_routes")
        mock_ok(api, body)

        result = make_provider(clock).routes(BOULDER, FORT_COLLINS)

        assert result.snap_distance_m == max(w["distance"] for w in body["waypoints"])
        assert result.snap_distance_m > 0

    def test_a_single_route_response(self, api: respx.MockRouter, clock: FakeClock) -> None:
        mock_ok(api, fixture("one_route"))

        result = make_provider(clock).routes(DENVER, COLORADO_SPRINGS)

        assert len(result.routes) == 1

    def test_three_routes(self, api: respx.MockRouter, clock: FakeClock) -> None:
        # The public server rarely returns three alternatives, so a third route is derived
        # from the recorded second one: slower and a little longer.
        body = fixture("two_routes")
        third = copy.deepcopy(body["routes"][1])
        third["duration"] += 120.0
        third["distance"] += 900.0
        body["routes"].append(third)
        mock_ok(api, body)

        result = make_provider(clock).routes(BOULDER, FORT_COLLINS)

        assert [round(r.duration_s) for r in result.routes] == [
            round(body["routes"][0]["duration"]),
            round(body["routes"][1]["duration"]),
            round(third["duration"]),
        ]

    def test_the_request_asks_for_alternatives_and_full_annotated_geometry(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = mock_ok(api, fixture("two_routes"))

        make_provider(clock).routes(BOULDER, FORT_COLLINS)

        url = route.calls.last.request.url
        assert url.path == "/route/v1/driving/-105.270500,40.015000;-105.084400,40.585300"
        assert dict(url.params) == {
            "alternatives": "3",
            "overview": "full",
            "geometries": "geojson",
            "annotations": "distance,duration",
            "steps": "false",
        }

    def test_a_trailing_slash_in_the_base_url_is_ignored(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = mock_ok(api, fixture("two_routes"))

        make_provider(clock, base_url=f"https://{HOST}/").routes(BOULDER, FORT_COLLINS)

        assert route.calls.last.request.url.path.startswith("/route/v1/driving/")

    def test_a_base_url_outside_the_allowlist_is_refused(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        with pytest.raises(HostNotAllowed):
            make_provider(clock, base_url="https://evil.example").routes(BOULDER, FORT_COLLINS)

    def test_it_satisfies_the_routing_provider_protocol(self, clock: FakeClock) -> None:
        provider: RoutingProvider = make_provider(clock)

        assert provider.name == "osrm"


class TestRouteVia:
    def test_maps_a_route_made_of_two_legs(self, api: respx.MockRouter, clock: FakeClock) -> None:
        body = fixture("via_waypoint")
        mock_ok(api, body)

        result = make_provider(clock).route_via(DENVER, WAYPOINT, BOULDER)

        assert len(result.routes) == 1
        route = result.routes[0]
        legs = body["routes"][0]["legs"]
        assert len(legs) == 2
        assert len(route.segment_durations_s) == sum(
            len(leg["annotation"]["duration"]) for leg in legs
        )
        assert len(route.segment_durations_s) == len(route.points) - 1
        assert result.snap_distance_m == max(w["distance"] for w in body["waypoints"])

    def test_the_request_goes_through_the_waypoint_without_alternatives(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = mock_ok(api, fixture("via_waypoint"))

        make_provider(clock).route_via(DENVER, WAYPOINT, BOULDER)

        url = route.calls.last.request.url
        assert url.path == (
            "/route/v1/driving/-104.990300,39.739200;-105.050000,39.950000;-105.270500,40.015000"
        )
        assert url.params["alternatives"] == "false"


class TestNoRoute:
    def test_http_400_with_no_route_code(self, api: respx.MockRouter, clock: FakeClock) -> None:
        api.get(host=HOST).respond(400, json=fixture("no_route"))

        with pytest.raises(NoRoute, match="Impossible route"):
            make_provider(clock).routes(DENVER, LatLon(21.3069, -157.8583))

    def test_http_400_with_no_segment_code(self, api: respx.MockRouter, clock: FakeClock) -> None:
        api.get(host=HOST).respond(400, json={"code": "NoSegment", "message": "no segment"})

        with pytest.raises(NoRoute):
            make_provider(clock).routes(DENVER, COLORADO_SPRINGS)

    def test_a_no_route_code_in_a_200_response(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        mock_ok(api, {"code": "NoRoute", "message": "Impossible route between points"})

        with pytest.raises(NoRoute):
            make_provider(clock).routes(DENVER, COLORADO_SPRINGS)

    def test_no_route_is_not_held_against_the_provider(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        provider = make_provider(clock)
        api.get(host=HOST).respond(400, json=fixture("no_route"))
        for _ in range(5):
            with pytest.raises(NoRoute):
                provider.routes(DENVER, COLORADO_SPRINGS)
        api.get(host=HOST).respond(200, json=fixture("one_route"))

        assert len(provider.routes(DENVER, COLORADO_SPRINGS).routes) == 1

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(400, json={"code": "InvalidQuery", "message": "bad"}),
            httpx.Response(400, text="Bad Request"),
            httpx.Response(400, json=["NoRoute"]),
            httpx.Response(403, json={"code": "NoRoute"}),
        ],
        ids=["other-code", "not-json", "not-an-object", "other-status"],
    )
    def test_other_rejections_stay_upstream_errors(
        self, api: respx.MockRouter, clock: FakeClock, response: httpx.Response
    ) -> None:
        api.get(host=HOST).mock(return_value=response)

        with pytest.raises(UpstreamError) as raised:
            make_provider(clock).routes(DENVER, COLORADO_SPRINGS)

        assert type(raised.value) is UpstreamError

    def test_outages_pass_through_unchanged(self, api: respx.MockRouter, clock: FakeClock) -> None:
        api.get(host=HOST).respond(503)
        with pytest.raises(UpstreamUnavailable):
            make_provider(clock).routes(DENVER, COLORADO_SPRINGS)

        api.get(host=HOST).mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(UpstreamTimeout):
            make_provider(clock).routes(DENVER, COLORADO_SPRINGS)


def broken(**changes: Any) -> dict[str, Any]:
    """The two-route fixture with its first route altered by ``changes`` (``None`` deletes)."""
    body = fixture("two_routes")
    for key, value in changes.items():
        if value is None:
            del body["routes"][0][key]
        else:
            body["routes"][0][key] = value
    return body


def with_geometry(**changes: Any) -> dict[str, Any]:
    body = fixture("two_routes")
    body["routes"][0]["geometry"].update(changes)
    return body


def with_annotation(**changes: Any) -> dict[str, Any]:
    body = fixture("two_routes")
    body["routes"][0]["legs"][0]["annotation"].update(changes)
    return body


def with_waypoints(waypoints: object) -> dict[str, Any]:
    body = fixture("two_routes")
    body["waypoints"] = waypoints
    return body


MALFORMED: dict[str, Any] = {
    "array": [],
    "no-code": {"routes": []},
    "error-code": {"code": "InvalidQuery", "message": "bad query"},
    "no-routes-key": {"code": "Ok", "waypoints": [{"distance": 1.0}]},
    "empty-routes": {"code": "Ok", "routes": [], "waypoints": [{"distance": 1.0}]},
    "routes-not-a-list": {"code": "Ok", "routes": {}, "waypoints": [{"distance": 1.0}]},
    "route-not-an-object": {"code": "Ok", "routes": [1], "waypoints": [{"distance": 1.0}]},
    "no-geometry": broken(geometry=None),
    "point-geometry": with_geometry(type="Point"),
    "coordinates-not-a-list": with_geometry(coordinates="abc"),
    "one-coordinate": with_geometry(coordinates=[[-105.0, 40.0]]),
    "short-coordinate": with_geometry(coordinates=[[-105.0], [-105.1, 40.1]]),
    "longitude-out-of-range": with_geometry(coordinates=[[-505.0, 40.0], [-105.0, 40.1]]),
    "text-coordinate": with_geometry(coordinates=[["x", 40.0], [-105.0, 40.1]]),
    "no-distance": broken(distance=None),
    "text-distance": broken(distance="far"),
    "negative-duration": broken(duration=-5.0),
    "boolean-duration": broken(duration=True),
    "no-legs": broken(legs=None),
    "leg-not-an-object": broken(legs=[3]),
    "leg-without-annotation": broken(legs=[{"distance": 1.0}]),
    "short-duration-annotation": with_annotation(duration=[1.0, 2.0]),
    "short-distance-annotation": with_annotation(distance=[1.0]),
    "extra-duration-annotation": with_annotation(
        duration=[*fixture("two_routes")["routes"][0]["legs"][0]["annotation"]["duration"], 1.0]
    ),
    "extra-distance-annotation": with_annotation(
        distance=[*fixture("two_routes")["routes"][0]["legs"][0]["annotation"]["distance"], 1.0]
    ),
    "single-point-route": {
        **fixture("two_routes"),
        "routes": [
            {
                **fixture("two_routes")["routes"][0],
                "geometry": {"type": "LineString", "coordinates": [[-105.27, 40.01]]},
                "legs": [{"annotation": {"duration": [], "distance": []}}],
            }
        ],
    },
    "unknown-code-with-valid-routes": {**fixture("two_routes"), "code": "Weird"},
    "text-in-annotation": with_annotation(duration="oops"),
    "negative-in-annotation": with_annotation(
        duration=[-1.0]
        * len(fixture("two_routes")["routes"][0]["legs"][0]["annotation"]["duration"])
    ),
    "no-waypoints": with_waypoints(None),
    "empty-waypoints": with_waypoints([]),
    "waypoint-not-an-object": with_waypoints([7]),
    "waypoint-without-distance": with_waypoints([{"name": "x"}]),
    "waypoint-text-distance": with_waypoints([{"distance": "near"}]),
}


class TestMalformedResponses:
    @pytest.mark.parametrize("body", list(MALFORMED.values()), ids=list(MALFORMED))
    def test_unusable_bodies_are_contract_errors(
        self, api: respx.MockRouter, clock: FakeClock, body: Any
    ) -> None:
        mock_ok(api, body)

        with pytest.raises(UpstreamContractError):
            make_provider(clock).routes(BOULDER, FORT_COLLINS)

    @pytest.mark.parametrize("text", ["<html>maintenance</html>", "", "NaN"])
    def test_bodies_that_are_not_json_objects(
        self, api: respx.MockRouter, clock: FakeClock, text: str
    ) -> None:
        api.get(host=HOST).respond(200, text=text)

        with pytest.raises(UpstreamContractError):
            make_provider(clock).routes(BOULDER, FORT_COLLINS)

    @pytest.mark.parametrize(
        ("path", "key"),
        [("route", "duration"), ("route", "distance"), ("waypoint", "distance")],
    )
    def test_a_non_finite_number_is_refused(
        self, api: respx.MockRouter, clock: FakeClock, path: str, key: str
    ) -> None:
        body = fixture("two_routes")
        target = body["routes"][0] if path == "route" else body["waypoints"][0]
        target[key] = float("nan")
        api.get(host=HOST).respond(200, text=json.dumps(body))  # json.dumps writes NaN

        with pytest.raises(UpstreamContractError, match="finite"):
            make_provider(clock).routes(BOULDER, FORT_COLLINS)

    def test_the_error_names_the_provider(self, api: respx.MockRouter, clock: FakeClock) -> None:
        mock_ok(api, {"code": "InvalidQuery"})

        with pytest.raises(UpstreamContractError) as raised:
            make_provider(clock).routes(BOULDER, FORT_COLLINS)

        assert raised.value.provider == "osrm"


class TestRequestSpacing:
    def test_consecutive_calls_are_kept_1_1_seconds_apart(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        mock_ok(api, fixture("two_routes"))
        spacing = MinSpacing(1.1, "osrm", clock, clock.sleep)
        provider = make_provider(clock, gates={"osrm": spacing})

        provider.routes(BOULDER, FORT_COLLINS)
        provider.route_via(BOULDER, WAYPOINT, FORT_COLLINS)

        assert clock.sleeps == [pytest.approx(1.1)]
