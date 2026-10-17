import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from rest_framework.exceptions import Throttled
from rest_framework.test import APIClient

from planner.api.serializers import ErrorEnvelopeSerializer, PlanResponseSerializer
from planner.domain.geometry import destination_point
from planner.domain.risk import WindBasis
from planner.infra.errors import (
    UpstreamContractError,
    UpstreamError,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from planner.providers.protocols import NoRoute
from planner.services.plan import PlanService
from tests.infra.fakes import FakeClock
from tests.services.stubs import START, StubRouting, StubWeather, route

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
ORIGIN = {"lat": START.lat, "lon": START.lon, "label": "Boulder, CO"}
DESTINATION = {
    "lat": destination_point(START, 90.0, 96_000).lat,
    "lon": destination_point(START, 90.0, 96_000).lon,
    "label": "East of Boulder",
}


def valid_body(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "origin": ORIGIN,
        "destination": DESTINATION,
        "departure_at": "2026-10-18T14:00:00Z",
        "load_lb": 42_000,
        "interval_mi": 25,
    }
    for key, value in changes.items():
        if value is ...:
            del values[key]
        else:
            values[key] = value
    return values


def three_routes() -> list[Any]:
    return [
        route(60, 55),
        route(62, 52, origin=destination_point(START, 0.0, 20_000)),
        route(65, 50, origin=destination_point(START, 180.0, 20_000)),
    ]


@pytest.fixture
def install(monkeypatch: pytest.MonkeyPatch) -> Any:  # noqa: ANN401
    """Install a plan service with scripted providers behind the endpoint."""

    def install_service(
        routing: StubRouting | None = None, weather: StubWeather | None = None
    ) -> PlanService:
        service = PlanService(
            routing or StubRouting(three_routes()),
            weather or StubWeather(),
            max_speed_mph=65.0,
            wind_basis=WindBasis.SUSTAINED,
            now=lambda: NOW,
            monotonic=FakeClock(),
        )
        monkeypatch.setattr(
            "planner.api.views.get_container", lambda: SimpleNamespace(plan_service=service)
        )
        monkeypatch.setattr("planner.api.views.utc_now", lambda: NOW)
        return service

    return install_service


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def post(client: APIClient, body: Any, **extra: Any) -> Any:  # noqa: ANN401
    return client.post("/api/plan", data=json.dumps(body), content_type="application/json", **extra)


class TestASuccessfulPlan:
    def test_it_returns_the_documented_response(self, client: APIClient, install: Any) -> None:
        install()

        response = post(client, valid_body())

        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"
        body = response.json()
        assert PlanResponseSerializer(data=body).is_valid()
        assert len(body["routes"]) == 3
        assert body["recommended_route_id"] == body["routes"][0]["id"]
        assert len(body["heatmap"]["frames"]) == 49

    def test_the_request_id_is_in_the_header_and_the_meta(
        self, client: APIClient, install: Any
    ) -> None:
        install()

        response = post(client, valid_body(), headers={"X-Request-ID": "trace-77"})

        assert response["X-Request-ID"] == "trace-77"
        assert response.json()["meta"]["request_id"] == "trace-77"

    def test_a_generated_request_id_is_also_in_the_meta(
        self, client: APIClient, install: Any
    ) -> None:
        install()

        response = post(client, valid_body())

        assert response.json()["meta"]["request_id"] == response["X-Request-ID"]

    def test_plans_are_not_cached(self, client: APIClient, install: Any) -> None:
        install()

        assert post(client, valid_body())["Cache-Control"] == "no-store"

    def test_the_request_reaches_the_service_as_a_plan_request(
        self, client: APIClient, install: Any
    ) -> None:
        routing = StubRouting(three_routes())
        install(routing)

        post(client, valid_body())

        kind, points = routing.calls[0]
        assert kind == "routes"
        assert points[0].lat == pytest.approx(ORIGIN["lat"])
        assert points[1].lon == pytest.approx(DESTINATION["lon"])

    def test_the_load_and_interval_are_used(self, client: APIClient, install: Any) -> None:
        install(weather=StubWeather(lambda place: {"wind": 50.0} if place.lat == 40.0 else {}))

        light = post(client, valid_body(load_lb=20_000, interval_mi=50)).json()
        heavy = post(client, valid_body(load_lb=45_000, interval_mi=10)).json()

        light_levels = {c["level"] for r in light["routes"] for c in r["checkpoints"]}
        heavy_levels = {c["level"] for r in heavy["routes"] for c in r["checkpoints"]}
        assert "SEVERE" in light_levels
        assert "NO_TRAVEL" in heavy_levels
        assert len(heavy["routes"][0]["checkpoints"]) > len(light["routes"][0]["checkpoints"])

    def test_a_departure_a_few_minutes_ago_is_planned_from_now(
        self, client: APIClient, install: Any
    ) -> None:
        install()
        recent = (NOW - timedelta(minutes=5)).isoformat()

        body = post(client, valid_body(departure_at=recent)).json()

        assert body["routes"][0]["checkpoints"][0]["eta"] == "2026-10-17T12:00:00Z"

    def test_a_weather_outage_is_a_200_with_a_banner(self, client: APIClient, install: Any) -> None:
        install(weather=StubWeather(lambda place: None))

        response = post(client, valid_body())

        assert response.status_code == 200
        assert response.json()["banner"] == "WEATHER_UNAVAILABLE"
        assert response.json()["routes"][0]["checkpoints"][0]["level"] == "UNKNOWN"

    def test_the_labels_are_accepted_but_not_echoed(self, client: APIClient, install: Any) -> None:
        install()

        response = post(client, valid_body())

        assert "Boulder, CO" not in response.content.decode()


VALIDATION_CASES: list[tuple[str, dict[str, Any], str]] = [
    ("missing origin", valid_body(origin=...), "origin"),
    ("missing destination", valid_body(destination=...), "destination"),
    ("origin latitude too high", valid_body(origin={**ORIGIN, "lat": 90.1}), "origin.lat"),
    ("origin latitude too low", valid_body(origin={**ORIGIN, "lat": -90.1}), "origin.lat"),
    ("origin longitude too high", valid_body(origin={**ORIGIN, "lon": 180.1}), "origin.lon"),
    ("origin longitude too low", valid_body(origin={**ORIGIN, "lon": -180.1}), "origin.lon"),
    ("destination latitude", valid_body(destination={**DESTINATION, "lat": 91}), "destination.lat"),
    (
        "destination longitude",
        valid_body(destination={**DESTINATION, "lon": 181}),
        "destination.lon",
    ),
    ("latitude as text", valid_body(origin={**ORIGIN, "lat": "40.0"}), "origin.lat"),
    ("label too long", valid_body(origin={**ORIGIN, "label": "x" * 201}), "origin.label"),
    (
        "destination label too long",
        valid_body(destination={**DESTINATION, "label": "x" * 201}),
        "destination.label",
    ),
    ("departure without offset", valid_body(departure_at="2026-10-18T14:00:00"), "departure_at"),
    ("departure not a time", valid_body(departure_at="soon"), "departure_at"),
    ("departure missing", valid_body(departure_at=...), "departure_at"),
    ("departure too far ahead", valid_body(departure_at="2026-10-24T12:00:01Z"), "departure_at"),
    ("departure in the past", valid_body(departure_at="2026-10-17T11:44:59Z"), "departure_at"),
    ("load negative", valid_body(load_lb=-1), "load_lb"),
    ("load too high", valid_body(load_lb=200_001), "load_lb"),
    ("load fractional", valid_body(load_lb=100.5), "load_lb"),
    ("load as text", valid_body(load_lb="42000"), "load_lb"),
    ("load missing", valid_body(load_lb=...), "load_lb"),
    ("interval not allowed", valid_body(interval_mi=30), "interval_mi"),
    ("interval as text", valid_body(interval_mi="25"), "interval_mi"),
    ("interval missing", valid_body(interval_mi=...), "interval_mi"),
    ("unknown field", {**valid_body(), "weight": 5}, "weight"),
]


class TestValidation:
    @pytest.mark.parametrize(
        ("body", "field"),
        [(case[1], case[2]) for case in VALIDATION_CASES],
        ids=[c[0] for c in VALIDATION_CASES],
    )
    def test_each_rule_gives_a_400_naming_the_field(
        self, client: APIClient, install: Any, body: dict[str, Any], field: str
    ) -> None:
        routing = StubRouting(three_routes())
        install(routing)

        response = post(client, body, headers={"X-Request-ID": "trace-1"})

        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "VALIDATION"
        assert error["field"] == field
        assert error["message"]
        assert error["request_id"] == "trace-1"
        assert ErrorEnvelopeSerializer(data=response.json()).is_valid()
        assert routing.calls == []  # nothing was asked of any provider

    @pytest.mark.parametrize(
        "body",
        [
            valid_body(origin={**ORIGIN, "lat": 90}),
            valid_body(origin={**ORIGIN, "lon": -180}),
            valid_body(origin={**ORIGIN, "label": "x" * 200}),
            valid_body(load_lb=0),
            valid_body(load_lb=200_000),
            valid_body(interval_mi=10),
            valid_body(departure_at="2026-10-24T12:00:00Z"),
            valid_body(departure_at="2026-10-17T11:45:00Z"),
            valid_body(origin={"lat": 40.0, "lon": -105.0}),
        ],
        ids=[
            "lat 90",
            "lon -180",
            "label 200",
            "load 0",
            "load 200000",
            "interval 10",
            "exactly 7 days",
            "exactly 15 minutes ago",
            "no label",
        ],
    )
    def test_the_edges_of_every_rule_are_accepted(
        self, client: APIClient, install: Any, body: dict[str, Any]
    ) -> None:
        install()

        assert post(client, body).status_code == 200

    def test_a_body_that_is_not_json_is_a_400(self, client: APIClient, install: Any) -> None:
        install()

        response = client.post("/api/plan", data="{not json", content_type="application/json")

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION"
        assert response.json()["error"]["message"] == "The request body is not valid JSON"

    def test_nan_in_a_body_is_a_400(self, client: APIClient, install: Any) -> None:
        install()
        text = json.dumps(valid_body()).replace("42000", "NaN")

        response = client.post("/api/plan", data=text, content_type="application/json")

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION"

    @pytest.mark.parametrize("text", ["[]", '"text"', "5", "null"])
    def test_a_body_that_is_not_an_object_is_a_400(
        self, client: APIClient, install: Any, text: str
    ) -> None:
        install()

        response = client.post("/api/plan", data=text, content_type="application/json")

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION"
        assert response.json()["error"]["field"] is None

    def test_an_empty_body_is_a_400(self, client: APIClient, install: Any) -> None:
        install()

        response = client.post("/api/plan", data="", content_type="application/json")

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION"

    @pytest.mark.parametrize(
        "content_type", ["text/plain", "application/x-www-form-urlencoded", "text/xml"]
    )
    def test_another_content_type_is_a_415(
        self, client: APIClient, install: Any, content_type: str
    ) -> None:
        install()

        response = client.post("/api/plan", data="origin=1", content_type=content_type)

        assert response.status_code == 415
        assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"

    def test_other_methods_are_a_405(self, client: APIClient, install: Any) -> None:
        install()

        for method in ("get", "put", "patch", "delete"):
            response = getattr(client, method)("/api/plan")

            assert response.status_code == 405
            assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
            assert "POST" in response["Allow"]


class TestErrorCodes:
    def test_a_trip_under_a_mile_is_too_close(self, client: APIClient, install: Any) -> None:
        routing = StubRouting(three_routes())
        install(routing)
        close = destination_point(START, 90.0, 800)

        response = post(
            client,
            valid_body(destination={"lat": close.lat, "lon": close.lon}),
            headers={"X-Request-ID": "trace-2"},
        )

        assert response.status_code == 400
        assert response.json()["error"] == {
            "code": "TOO_CLOSE",
            "message": "Origin and destination must be at least 1 mile apart",
            "field": None,
            "request_id": "trace-2",
        }
        assert routing.calls == []

    @pytest.mark.parametrize(
        ("failure", "status", "code"),
        [
            (NoRoute("none"), 422, "NO_ROUTE"),
            (UpstreamUnavailable("osrm", "down"), 503, "UPSTREAM_UNAVAILABLE"),
            (UpstreamTimeout("osrm", "slow"), 504, "UPSTREAM_TIMEOUT"),
            (UpstreamContractError("osrm", "garbage"), 502, "UPSTREAM_ERROR"),
            (UpstreamError("osrm", "HTTP 400", status=400), 502, "UPSTREAM_ERROR"),
        ],
        ids=["no route", "unavailable", "timeout", "contract error", "rejected"],
    )
    def test_routing_failures_map_to_their_status_and_code(
        self, client: APIClient, install: Any, failure: Exception, status: int, code: str
    ) -> None:
        install(StubRouting(three_routes(), outcome=failure))

        response = post(client, valid_body(), headers={"X-Request-ID": "trace-3"})

        assert response.status_code == status
        assert response.json()["error"]["code"] == code
        assert response.json()["error"]["request_id"] == "trace-3"
        assert response["X-Request-ID"] == "trace-3"
        assert ErrorEnvelopeSerializer(data=response.json()).is_valid()

    def test_a_weather_contract_error_is_a_502(self, client: APIClient, install: Any) -> None:
        class BrokenWeather(StubWeather):
            def hourly(self, points, first_day, last_day):  # type: ignore[no-untyped-def]  # noqa: ANN001, ANN201
                raise UpstreamContractError("open-meteo", "wrong units")

        install(weather=BrokenWeather())

        response = post(client, valid_body())

        assert response.status_code == 502
        assert response.json()["error"]["code"] == "UPSTREAM_ERROR"

    def test_rate_limiting_is_a_429_with_retry_after(self, client: APIClient, install: Any) -> None:
        install(StubRouting(three_routes(), outcome=Throttled(wait=12)))

        response = post(client, valid_body())

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "RATE_LIMITED"
        assert response["Retry-After"] == "12"

    def test_an_unexpected_failure_is_a_500_that_says_nothing_about_it(
        self, client: APIClient, install: Any
    ) -> None:
        install(StubRouting(three_routes(), outcome=RuntimeError("secret internals 39.7,-105.0")))

        response = post(client, valid_body())

        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "secret" not in response.content.decode()
        assert "39.7" not in response.content.decode()

    def test_error_responses_are_never_html(self, client: APIClient, install: Any) -> None:
        install(StubRouting(three_routes(), outcome=RuntimeError("x")))

        for response in (post(client, valid_body()), client.get("/api/missing")):
            assert response["Content-Type"].startswith("application/json")
            assert "error" in response.json()
