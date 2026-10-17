from types import SimpleNamespace
from typing import Any

import pytest
from rest_framework.test import APIClient

from planner.domain.risk import WindBasis
from planner.services.plan import PlanService
from tests.api.helpers import NOW, three_routes
from tests.infra.fakes import FakeClock
from tests.services.stubs import StubRouting, StubWeather


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
