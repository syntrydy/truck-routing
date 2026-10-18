import json
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    response = APIClient().get("/api/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
    assert response.status_code == 200
    return json.loads(response.content)  # type: ignore[no-any-return]


def test_the_schema_validates_without_warnings(tmp_path: Path) -> None:
    out = tmp_path / "schema.yml"
    errors = StringIO()

    call_command("spectacular", "--validate", "--fail-on-warn", "--file", str(out), stderr=errors)

    assert out.read_text().startswith("openapi:")
    assert errors.getvalue() == ""


def test_the_plan_operation_is_a_post(schema: dict[str, Any]) -> None:
    operation = schema["paths"]["/api/plan"]["post"]

    assert set(schema["paths"]["/api/plan"]) == {"post"}
    assert operation["operationId"] == "plan"
    assert operation["summary"] == "Plan a trip"


def test_the_request_body_is_the_plan_request(schema: dict[str, Any]) -> None:
    body = schema["paths"]["/api/plan"]["post"]["requestBody"]["content"]["application/json"]

    assert body["schema"] == {"$ref": "#/components/schemas/PlanRequest"}


def test_the_plan_request_component_describes_every_field(schema: dict[str, Any]) -> None:
    component = schema["components"]["schemas"]["PlanRequest"]

    assert set(component["properties"]) == {
        "origin",
        "destination",
        "departure_at",
        "load_lb",
        "interval_mi",
    }
    assert set(component["required"]) == set(component["properties"])
    assert schema["components"]["schemas"]["Point"]["properties"]["lat"]["maximum"] == 90
    assert schema["components"]["schemas"]["Point"]["properties"]["lon"]["minimum"] == -180
    assert component["properties"]["load_lb"]["maximum"] == 200_000
    assert component["properties"]["load_lb"]["minimum"] == 0


def test_the_success_response_is_the_plan_response(schema: dict[str, Any]) -> None:
    responses = schema["paths"]["/api/plan"]["post"]["responses"]

    assert responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/PlanResponse"
    }


def test_every_error_status_uses_the_error_envelope(schema: dict[str, Any]) -> None:
    responses = schema["paths"]["/api/plan"]["post"]["responses"]

    for status in ("400", "422", "429", "502", "503", "504"):
        assert responses[status]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorEnvelope"
        }, status
        assert responses[status]["description"]


def test_the_error_codes_are_documented_on_their_statuses(schema: dict[str, Any]) -> None:
    responses = schema["paths"]["/api/plan"]["post"]["responses"]

    assert "VALIDATION" in responses["400"]["description"]
    assert "TOO_CLOSE" in responses["400"]["description"]
    assert "NO_ROUTE" in responses["422"]["description"]
    assert "UPSTREAM_UNAVAILABLE" in responses["503"]["description"]
    assert "UPSTREAM_TIMEOUT" in responses["504"]["description"]


def test_the_response_components_exist(schema: dict[str, Any]) -> None:
    components = schema["components"]["schemas"]

    for name in (
        "PlanResponse",
        "Route",
        "Checkpoint",
        "Summary",
        "Geometry",
        "Heatmap",
        "HeatmapFrame",
        "Meta",
        "ErrorEnvelope",
        "ErrorDetail",
    ):
        assert name in components, name


def test_the_levels_and_banners_are_named_enums(schema: dict[str, Any]) -> None:
    components = schema["components"]["schemas"]

    assert components["RiskLevelEnum"]["enum"] == [
        "UNKNOWN",
        "LOW",
        "MODERATE",
        "HIGH",
        "SEVERE",
        "NO_TRAVEL",
    ]
    banner = components["PlanResponse"]["properties"]["banner"]
    assert components["BannerEnum"]["enum"] == ["NO_SAFE_ROUTE", "WEATHER_UNAVAILABLE"]
    assert banner["nullable"] is True
    assert components["Checkpoint"]["properties"]["level"] == {
        "$ref": "#/components/schemas/RiskLevelEnum"
    }
    assert components["Summary"]["properties"]["worst_level"] == {
        "$ref": "#/components/schemas/RiskLevelEnum"
    }


def test_the_response_has_the_documented_top_level_fields(schema: dict[str, Any]) -> None:
    properties = schema["components"]["schemas"]["PlanResponse"]["properties"]

    assert set(properties) == {
        "recommended_route_id",
        "recommendation_reason",
        "ranking",
        "banner",
        "routes",
        "heatmap",
        "notes",
        "meta",
    }


def test_the_departure_is_a_date_time_string(schema: dict[str, Any]) -> None:
    departure = schema["components"]["schemas"]["PlanRequest"]["properties"]["departure_at"]

    assert departure == {"type": "string", "format": "date-time"}


def test_the_health_endpoint_is_still_documented(schema: dict[str, Any]) -> None:
    assert "get" in schema["paths"]["/api/health"]


def test_the_schema_lists_nothing_that_does_not_exist(schema: dict[str, Any]) -> None:
    assert set(schema["paths"]) == {
        "/api/health",
        "/api/ready",
        "/api/geocode",
        "/api/demo",
        "/api/plan",
    }


def test_the_geocode_operation_takes_a_required_query(schema: dict[str, Any]) -> None:
    operation = schema["paths"]["/api/geocode"]["get"]

    (query,) = operation["parameters"]
    assert (query["name"], query["in"], query["required"]) == ("q", "query", True)
    assert operation["operationId"] == "geocode"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/GeocodeResponse"
    }
    for status in ("400", "429", "502", "503", "504"):
        assert operation["responses"][status]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorEnvelope"
        }


def test_the_geocode_response_describes_a_place(schema: dict[str, Any]) -> None:
    place = schema["components"]["schemas"]["Place"]

    assert set(place["properties"]) == {"label", "lat", "lon", "kind"}
    assert set(place["required"]) == set(place["properties"])
    assert place["properties"]["kind"] == {"$ref": "#/components/schemas/PlaceKindEnum"}
    assert set(schema["components"]["schemas"]["PlaceKindEnum"]["enum"]) == {
        "city",
        "region",
        "country",
        "street",
        "address",
        "place",
    }


def test_the_ready_operation_describes_breakers_and_cache(schema: dict[str, Any]) -> None:
    operation = schema["paths"]["/api/ready"]["get"]
    ready = schema["components"]["schemas"]["Ready"]

    assert operation["operationId"] == "ready"
    assert set(ready["properties"]) == {"status", "cache", "providers"}
    assert set(ready["required"]) == set(ready["properties"])


def test_the_demo_is_documented_with_the_plan_response_and_its_two_parameters(
    schema: dict[str, Any],
) -> None:
    operation = schema["paths"]["/api/demo"]["get"]

    parameters = {parameter["name"] for parameter in operation["parameters"]}
    ok = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert parameters == {"load_lb", "interval_mi"}
    assert ok == {"$ref": "#/components/schemas/PlanResponse"}


def test_the_ranking_is_documented_as_criteria_with_a_value_for_each_route(
    schema: dict[str, Any],
) -> None:
    schemas = schema["components"]["schemas"]

    criterion = schemas["RankingCriterion"]["properties"]
    assert list(criterion) == ["id", "label", "unit", "decisive", "values"]
    assert schemas["RankingCriterionEnum"]["enum"] == [
        "NO_TRAVEL_MI",
        "SEVERE_MI",
        "HIGH_MI",
        "AVG_RISK",
        "DURATION",
    ]
    assert schemas["RankingUnitEnum"]["enum"] == ["mi", "risk", "s"]
    assert set(schemas["RankingValue"]["properties"]) == {"route_id", "value", "best"}
    assert schemas["RankingValue"]["properties"]["value"]["nullable"] is True
