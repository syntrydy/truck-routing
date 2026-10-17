import json
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

PHOTON = "photon.komoot.io"
NOMINATIM = "nominatim.openstreetmap.org"
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "geocode"


def fixture(name: str) -> Any:  # noqa: ANN401
    return json.loads((FIXTURES / f"{name}.json").read_text())


def search(client: APIClient, query: str | None = "denver", **extra: Any) -> Any:  # noqa: ANN401
    data = {} if query is None else {"q": query}
    return client.get("/api/geocode", data, **extra)


class TestGeocodeEndpoint:
    def test_it_returns_the_places_of_the_geocoder(self, client: APIClient, geocoding: Any) -> None:
        geocoding.router.get(host=PHOTON).respond(200, json=fixture("photon_city"))

        response = search(client)

        assert response.status_code == 200
        places = response.json()["results"]
        assert places[0] == {
            "label": "Denver, Colorado, United States",
            "lat": pytest.approx(39.74, abs=0.01),
            "lon": pytest.approx(-104.98, abs=0.01),
            "kind": "city",
        }
        assert set(places[0]) == {"label", "lat", "lon", "kind"}

    def test_nothing_found_is_an_empty_list(self, client: APIClient, geocoding: Any) -> None:
        geocoding.router.get(host=PHOTON).respond(200, json=fixture("photon_empty"))

        response = search(client, "qzxwvbnmpl")

        assert (response.status_code, response.json()) == (200, {"results": []})

    def test_at_most_eight_places_are_returned(self, client: APIClient, geocoding: Any) -> None:
        feature = fixture("photon_city")["features"][0]
        crowded = {
            "type": "FeatureCollection",
            "features": [
                {
                    **feature,
                    "geometry": {
                        "type": "Point",
                        "coordinates": [-104.0 - n, 39.0 + n / 10],
                    },
                    "properties": {**feature["properties"], "name": f"Denver {n}"},
                }
                for n in range(12)
            ],
        }
        geocoding.router.get(host=PHOTON).respond(200, json=crowded)

        assert len(search(client).json()["results"]) == 8

    def test_nominatim_answers_when_photon_is_down(self, client: APIClient, geocoding: Any) -> None:
        geocoding.router.get(host=PHOTON).respond(503)
        geocoding.router.get(host=NOMINATIM).respond(200, json=fixture("nominatim_city"))

        response = search(client)

        assert response.status_code == 200
        assert response.json()["results"][0]["label"] == "Denver, Colorado, United States"

    def test_a_repeated_query_does_not_call_the_geocoders_again(
        self, client: APIClient, geocoding: Any
    ) -> None:
        photon = geocoding.router.get(host=PHOTON).respond(200, json=fixture("photon_city"))

        search(client, "Denver")
        search(client, "  denver ")

        assert photon.call_count == 1

    @pytest.mark.parametrize("query", ["abc", "x" * 100])
    def test_the_shortest_and_the_longest_query_are_accepted(
        self, client: APIClient, geocoding: Any, query: str
    ) -> None:
        geocoding.router.get(host=PHOTON).respond(200, json=fixture("photon_empty"))

        assert search(client, query).status_code == 200

    def test_spacing_is_tidied_before_the_length_is_counted(
        self, client: APIClient, geocoding: Any
    ) -> None:
        geocoding.router.get(host=PHOTON).respond(200, json=fixture("photon_empty"))

        assert search(client, "  a      b  ").status_code == 200  # "a b": three characters
        assert search(client, "a      ").status_code == 400  # "a": one

    @pytest.mark.parametrize("query", [None, "", "  ", "ab", "x" * 101])
    def test_a_missing_or_badly_sized_query_is_a_validation_error(
        self, client: APIClient, geocoding: Any, query: str | None
    ) -> None:
        response = search(client, query)

        assert response.status_code == 400
        error = response.json()["error"]
        assert (error["code"], error["field"]) == ("VALIDATION", "q")
        assert "3 to 100" in error["message"]
        assert not geocoding.router.calls

    def test_every_geocoder_failing_is_an_upstream_error(
        self, client: APIClient, geocoding: Any
    ) -> None:
        geocoding.router.get(host=PHOTON).respond(503)
        geocoding.router.get(host=NOMINATIM).mock(side_effect=httpx.ReadTimeout("slow"))

        response = search(client)

        assert response.status_code == 504
        assert response.json()["error"]["code"] == "UPSTREAM_TIMEOUT"

    def test_only_get_is_allowed(self, client: APIClient, geocoding: Any) -> None:
        response = client.post("/api/geocode", {"q": "denver"}, format="json")

        assert response.status_code == 405


@pytest.fixture
def limited(settings: Any, monkeypatch: pytest.MonkeyPatch) -> Any:  # noqa: ANN401
    monkeypatch.setattr(time, "time", lambda: 1_800_000_030.0)
    settings.RATELIMIT_ENABLE = True
    settings.TRUSTED_PROXY_COUNT = 0
    cache.clear()
    yield
    cache.clear()


class TestGeocodeLimit:
    def test_sixty_requests_a_minute_are_allowed_and_the_next_is_not(
        self, client: APIClient, geocoding: Any, limited: Any
    ) -> None:
        geocoding.router.get(host=PHOTON).respond(200, json=fixture("photon_city"))

        statuses = [search(client, REMOTE_ADDR="203.0.113.9").status_code for _ in range(60)]
        refused = search(client, REMOTE_ADDR="203.0.113.9")

        assert set(statuses) == {200}
        assert refused.status_code == 429
        assert refused.json()["error"]["code"] == "RATE_LIMITED"
        assert refused["Retry-After"] == "60"

    def test_each_client_has_its_own_count(
        self, client: APIClient, geocoding: Any, limited: Any, settings: Any
    ) -> None:
        settings.GEOCODE_RATE_LIMIT = "2/m"
        geocoding.router.get(host=PHOTON).respond(200, json=fixture("photon_city"))

        for _ in range(2):
            search(client, REMOTE_ADDR="203.0.113.9")

        assert search(client, REMOTE_ADDR="203.0.113.9").status_code == 429
        assert search(client, REMOTE_ADDR="203.0.113.10").status_code == 200

    def test_geocode_and_plan_are_counted_separately(
        self, client: APIClient, geocoding: Any, limited: Any, settings: Any
    ) -> None:
        settings.GEOCODE_RATE_LIMIT = "1/m"
        settings.PLAN_RATE_LIMIT = "1/m"
        geocoding.router.get(host=PHOTON).respond(200, json=fixture("photon_city"))
        search(client, REMOTE_ADDR="203.0.113.9")

        def plan() -> int:
            return client.post(
                "/api/plan", {}, format="json", REMOTE_ADDR="203.0.113.9"
            ).status_code

        assert plan() == 400  # refused for its body, not for its rate
        assert plan() == 429
        assert search(client, REMOTE_ADDR="203.0.113.9").status_code == 429
