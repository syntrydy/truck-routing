from rest_framework.test import APIClient

from planner.api.serializers import PlanResponseSerializer

DEMO = "/api/demo"
DANGEROUS = {"HIGH", "SEVERE", "NO_TRAVEL"}


def worst_levels(body: dict) -> set[str]:  # type: ignore[type-arg]
    return {c["level"] for route in body["routes"] for c in route["checkpoints"]}


class TestTheDemoEndpoint:
    def test_it_returns_a_plan_in_the_documented_shape_from_the_demo_providers(
        self, client: APIClient
    ) -> None:
        response = client.get(DEMO)

        assert response.status_code == 200
        assert response["Cache-Control"] == "no-store"
        body = response.json()
        assert PlanResponseSerializer(data=body).is_valid()
        assert len(body["routes"]) == 3
        assert len(body["heatmap"]["frames"]) == 49
        assert body["meta"]["routing_source"] == "demo"
        assert body["meta"]["weather_source"] == "demo"

    def test_the_storm_shows_danger_on_the_demo_trip(self, client: APIClient) -> None:
        body = client.get(DEMO).json()

        assert DANGEROUS & worst_levels(body)
        assert "NO_TRAVEL" in worst_levels(body)

    def test_a_lighter_load_is_safer_in_the_same_storm(self, client: APIClient) -> None:
        heavy = worst_levels(client.get(DEMO, {"load_lb": 42_000}).json())
        light = worst_levels(client.get(DEMO, {"load_lb": 10_000}).json())

        assert "NO_TRAVEL" in heavy
        assert "NO_TRAVEL" not in light

    def test_the_checkpoint_spacing_is_honoured(self, client: APIClient) -> None:
        wide = client.get(DEMO, {"interval_mi": 50}).json()
        narrow = client.get(DEMO, {"interval_mi": 10}).json()

        assert len(narrow["routes"][0]["checkpoints"]) > len(wide["routes"][0]["checkpoints"])

    def test_a_load_over_the_limit_is_a_validation_error(self, client: APIClient) -> None:
        response = client.get(DEMO, {"load_lb": 300_000})

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION"
        assert response.json()["error"]["field"] == "load_lb"

    def test_a_spacing_that_is_not_offered_is_a_validation_error(self, client: APIClient) -> None:
        response = client.get(DEMO, {"interval_mi": 7})

        assert response.status_code == 400
        assert response.json()["error"]["field"] == "interval_mi"
