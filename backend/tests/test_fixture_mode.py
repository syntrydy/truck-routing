"""Fixture mode: the real adapters on recorded responses, and the guard against production."""

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from rest_framework.test import APIClient

from planner.infra.fixture_http import FixtureUpstream, UnrecordedRequest
from planner.services.container import get_container

BACKEND = Path(__file__).resolve().parents[1]
FIXTURES = BACKEND / "fixtures"


def import_settings(**env: str) -> subprocess.CompletedProcess[str]:
    """Import the settings in a fresh process, whatever a local .env says."""
    base = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "DEBUG": "false",
        "SECRET_KEY": "k" * 60,
        "PROVIDERS_MODE": "live",
        "ALLOW_FIXTURE_PROVIDERS": "false",
    }
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", "import config.settings"],
        cwd=BACKEND,
        env={**base, **env},
        capture_output=True,
        text=True,
        check=False,
    )


class TestTheGuard:
    def test_fixture_mode_is_refused_in_production(self) -> None:
        result = import_settings(PROVIDERS_MODE="fixtures")

        assert result.returncode != 0
        assert "PROVIDERS_MODE=fixtures needs DEBUG=True or ALLOW_FIXTURE_PROVIDERS=True" in (
            result.stderr
        )

    @pytest.mark.parametrize("env", [{"DEBUG": "true"}, {"ALLOW_FIXTURE_PROVIDERS": "true"}])
    def test_fixture_mode_is_allowed_in_development_or_when_said_so(
        self, env: dict[str, str]
    ) -> None:
        assert import_settings(PROVIDERS_MODE="fixtures", **env).returncode == 0

    def test_live_mode_needs_nothing(self) -> None:
        assert import_settings().returncode == 0

    def test_an_unknown_mode_is_refused(self) -> None:
        result = import_settings(PROVIDERS_MODE="record")

        assert result.returncode != 0
        assert 'PROVIDERS_MODE must be "live" or "fixtures"' in result.stderr


class TestTheRecordedUpstream:
    def get(self, url: str, **params: str) -> httpx.Response:
        return FixtureUpstream(FIXTURES).client().get(url, params=params)

    def test_routing_answers_with_the_recorded_routes(self) -> None:
        response = self.get("https://router.project-osrm.org/route/v1/driving/1,2;3,4")

        assert response.status_code == 200
        assert len(response.json()["routes"]) == 2

    def test_a_detour_through_a_via_point_has_no_route(self) -> None:
        response = self.get("https://router.project-osrm.org/route/v1/driving/1,2;3,4;5,6")

        assert response.status_code == 400
        assert response.json()["code"] == "NoRoute"

    def test_weather_covers_the_days_asked_for(self) -> None:
        response = self.get(
            "https://api.open-meteo.com/v1/forecast",
            latitude="40.0",
            longitude="-105.3",
            start_date="2030-01-05",
            end_date="2030-01-06",
        )

        times = response.json()["hourly"]["time"]
        assert len(times) == 48
        assert times[0] == 1893801600  # 2030-01-05 00:00 UTC
        assert {b - a for a, b in zip(times, times[1:], strict=False)} == {3600}

    def test_weather_for_several_places_is_a_list_in_request_order(self) -> None:
        response = self.get(
            "https://api.open-meteo.com/v1/forecast",
            latitude="40.0,40.5",
            longitude="-105.3,-105.1",
            start_date="2030-01-05",
            end_date="2030-01-05",
        )

        assert len(response.json()) == 2

    def test_the_geocoder_knows_the_two_recorded_cities(self) -> None:
        boulder = self.get("https://photon.komoot.io/api/", q="Boulder, CO").json()
        fort = self.get("https://photon.komoot.io/api/", q="fort collins").json()
        nowhere = self.get("https://photon.komoot.io/api/", q="atlantis").json()

        assert boulder["features"][0]["properties"]["name"] == "Boulder"
        assert fort["features"][0]["properties"]["name"] == "Fort Collins"
        assert nowhere["features"] == []

    def test_a_host_without_a_recording_fails_loudly(self) -> None:
        with pytest.raises(UnrecordedRequest, match="example.com"):
            self.get("https://example.com/")


class TestAPlanInFixtureMode:
    def test_the_api_plans_a_trip_without_the_network(self, settings: Any) -> None:
        settings.PROVIDERS_MODE = "fixtures"
        settings.FIXTURES_DIR = FIXTURES
        get_container.cache_clear()
        client = APIClient()
        try:
            places = client.get("/api/geocode", {"q": "boulder"}).json()["results"]
            response = client.post(
                "/api/plan",
                {
                    "origin": {"lat": places[0]["lat"], "lon": places[0]["lon"]},
                    "destination": {"lat": 40.5853, "lon": -105.0844},
                    "departure_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                    "load_lb": 20000,
                    "interval_mi": 10,
                },
                format="json",
            )
        finally:
            get_container.cache_clear()

        assert response.status_code == 200, response.content
        body = response.json()
        assert len(body["routes"]) == 2
        assert body["meta"]["routing_source"] == "osrm"
        assert body["meta"]["weather_source"] == "open-meteo"
        assert body["banner"] is None
