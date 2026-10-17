import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
import respx
from django.core.cache.backends.locmem import LocMemCache
from rest_framework.test import APIClient

from planner.domain.risk import WindBasis
from planner.infra.http import ProviderPolicy, UpstreamClient
from planner.services.container import build_container
from planner.services.plan import PlanService
from tests.api.helpers import NOW, three_routes
from tests.infra.fakes import FakeClock, FixedJitter
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


@pytest.fixture
def geocoding(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Install the real container (geocoder chain, client, cache) with Photon and Nominatim
    answering from ``respx`` routes, and yield the container and the mock router."""
    clock = FakeClock()
    client = UpstreamClient(
        [
            ProviderPolicy("photon", timeout_s=4.0, max_concurrency=2),
            ProviderPolicy("nominatim", timeout_s=4.0, max_concurrency=2),
        ],
        ["photon.komoot.io", "nominatim.openstreetmap.org"],
        "tests/1.0",
        clock=clock,
        sleep=clock.sleep,
        jitter=FixedJitter(1.0),
    )
    container = build_container(
        client=client,
        cache_backend=LocMemCache(f"geocoding-{uuid.uuid4().hex}", {}),
        ors_api_key="",
        max_speed_mph=65.0,
        wind_basis=WindBasis.SUSTAINED,
    )
    monkeypatch.setattr("planner.api.views.get_container", lambda: container)
    with respx.mock(assert_all_called=False) as router:
        yield SimpleNamespace(container=container, router=router, clock=clock)
