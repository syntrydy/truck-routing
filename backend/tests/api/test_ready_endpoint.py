import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from rest_framework.test import APIClient

PHOTON = "photon.komoot.io"
NOMINATIM = "nominatim.openstreetmap.org"
OK_PLACES = {"type": "FeatureCollection", "features": []}
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "geocode"


def fixture(name: str) -> Any:  # noqa: ANN401
    return json.loads((FIXTURES / f"{name}.json").read_text())


def drive_photon_open(client: APIClient, geocoding: Any) -> None:
    """Fail Photon until its circuit breaker opens (three failed requests)."""
    geocoding.router.get(host=PHOTON).respond(503)
    geocoding.router.get(host=NOMINATIM).respond(200, json=fixture("nominatim_city"))
    for n in range(3):
        client.get("/api/geocode", {"q": f"denver {n}"})


class TestReady:
    def test_everything_is_ok_at_the_start(self, client: APIClient, geocoding: Any) -> None:
        response = client.get("/api/ready")

        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "cache": True,
            "providers": {"nominatim": "closed", "photon": "closed"},
        }
        assert response["Cache-Control"] == "no-store"

    def test_it_makes_no_upstream_call(self, client: APIClient, geocoding: Any) -> None:
        client.get("/api/ready")

        assert not geocoding.router.calls

    def test_an_open_breaker_makes_it_degraded_but_still_200(
        self, client: APIClient, geocoding: Any
    ) -> None:
        drive_photon_open(client, geocoding)

        response = client.get("/api/ready")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"
        assert body["providers"]["photon"] == "open"
        assert body["providers"]["nominatim"] == "closed"

    def test_a_breaker_that_may_be_probed_is_half_open_and_degraded(
        self, client: APIClient, geocoding: Any
    ) -> None:
        drive_photon_open(client, geocoding)
        geocoding.clock.advance(61)

        body = client.get("/api/ready").json()

        assert body["providers"]["photon"] == "half_open"
        assert body["status"] == "degraded"

    def test_a_recovered_provider_closes_its_breaker(
        self, client: APIClient, geocoding: Any
    ) -> None:
        drive_photon_open(client, geocoding)
        geocoding.clock.advance(61)
        geocoding.router.get(host=PHOTON).respond(200, json=OK_PLACES)
        client.get("/api/geocode", {"q": "boulder"})

        body = client.get("/api/ready").json()

        assert (body["status"], body["providers"]["photon"]) == ("ok", "closed")

    def test_a_cache_that_fails_makes_it_degraded(
        self, client: APIClient, geocoding: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(*args: object, **kwargs: object) -> None:
            raise ConnectionError("cache down")

        monkeypatch.setattr(geocoding.container.cache._backend, "set", broken)  # noqa: SLF001

        response = client.get("/api/ready")

        assert response.status_code == 200
        body = response.json()
        assert (body["status"], body["cache"]) == ("degraded", False)
        assert set(body["providers"].values()) == {"closed"}

    def test_a_cache_that_forgets_makes_it_degraded(
        self, client: APIClient, geocoding: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(geocoding.container.cache._backend, "get", lambda *a, **k: None)  # noqa: SLF001

        assert client.get("/api/ready").json()["cache"] is False

    def test_a_timeout_does_not_matter_to_the_state_of_an_unused_provider(
        self, client: APIClient, geocoding: Any
    ) -> None:
        geocoding.router.get(host=PHOTON).mock(side_effect=httpx.ReadTimeout("slow"))
        geocoding.router.get(host=NOMINATIM).respond(200, json=fixture("nominatim_city"))

        client.get("/api/geocode", {"q": "denver"})

        assert client.get("/api/ready").json()["providers"]["nominatim"] == "closed"
