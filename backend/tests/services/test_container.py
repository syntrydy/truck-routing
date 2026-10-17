import uuid
from typing import Any

import pytest
from django.core.cache import caches
from django.core.cache.backends.locmem import LocMemCache
from django.core.exceptions import ImproperlyConfigured

from planner.domain.risk import WindBasis
from planner.infra.http import ProviderPolicy, UpstreamClient
from planner.providers.geocode_chain import CachedGeocoder
from planner.providers.routing_chain import FallbackRoutingProvider
from planner.providers.routing_osrm import OsrmRoutingProvider
from planner.providers.weather_openmeteo import OpenMeteoWeatherProvider
from planner.services.container import (
    Container,
    build_container,
    container_from_settings,
    get_container,
)
from planner.services.plan import PlanService


@pytest.fixture
def client() -> UpstreamClient:
    return UpstreamClient(
        [ProviderPolicy("osrm", timeout_s=8.0, max_concurrency=1)], [], "tests/1.0"
    )


def build(client: UpstreamClient, **overrides: Any) -> Container:
    values: dict[str, Any] = {
        "client": client,
        "cache_backend": LocMemCache(f"container-{uuid.uuid4()}", {}),
        "ors_api_key": "",
        "max_speed_mph": 65.0,
        "wind_basis": WindBasis.SUSTAINED,
    }
    values.update(overrides)
    return build_container(**values)


class TestBuildContainer:
    def test_the_container_holds_the_service_the_geocoder_and_the_shared_parts(
        self, client: UpstreamClient
    ) -> None:
        container = build(client)

        assert isinstance(container.plan_service, PlanService)
        assert isinstance(container.geocoder, CachedGeocoder)
        assert container.client is client

    def test_without_an_ors_key_routing_is_osrm_alone(self, client: UpstreamClient) -> None:
        service = build(client).plan_service

        assert isinstance(service._routing, OsrmRoutingProvider)  # noqa: SLF001

    def test_with_an_ors_key_routing_falls_back_to_openrouteservice(
        self, client: UpstreamClient
    ) -> None:
        service = build(client, ors_api_key="a-key").plan_service

        assert isinstance(service._routing, FallbackRoutingProvider)  # noqa: SLF001

    def test_weather_comes_from_open_meteo(self, client: UpstreamClient) -> None:
        service = build(client).plan_service

        assert isinstance(service._weather, OpenMeteoWeatherProvider)  # noqa: SLF001

    def test_the_plan_service_gets_the_speed_and_the_wind_basis(
        self, client: UpstreamClient
    ) -> None:
        service = build(client, max_speed_mph=55.0, wind_basis=WindBasis.GUST).plan_service

        assert service._max_speed_mph == 55.0  # noqa: SLF001
        assert service._wind_basis is WindBasis.GUST  # noqa: SLF001

    def test_the_weather_and_the_geocoder_share_one_cache_backend(
        self, client: UpstreamClient
    ) -> None:
        backend = LocMemCache(f"shared-{uuid.uuid4()}", {})

        container = build(client, cache_backend=backend)

        assert container.cache._backend is backend  # noqa: SLF001
        assert container.plan_service._weather._cache is container.cache  # type: ignore[attr-defined]  # noqa: SLF001
        assert container.geocoder._cache is container.cache  # type: ignore[attr-defined]  # noqa: SLF001


class TestFromSettings:
    def test_the_defaults_give_a_working_container(self, settings: Any) -> None:
        settings.ORS_API_KEY = ""

        container = container_from_settings()

        assert container.plan_service._max_speed_mph == 65.0  # noqa: SLF001
        assert container.plan_service._wind_basis is WindBasis.SUSTAINED  # noqa: SLF001
        assert isinstance(container.plan_service._routing, OsrmRoutingProvider)  # noqa: SLF001

    def test_the_settings_are_honoured(self, settings: Any) -> None:
        settings.ORS_API_KEY = "a-key"
        settings.TRUCK_MAX_SPEED_MPH = 60.0
        settings.RISK_WIND_BASIS = "gust"

        container = container_from_settings()

        assert isinstance(container.plan_service._routing, FallbackRoutingProvider)  # noqa: SLF001
        assert container.plan_service._max_speed_mph == 60.0  # noqa: SLF001
        assert container.plan_service._wind_basis is WindBasis.GUST  # noqa: SLF001

    def test_the_client_is_built_from_the_upstream_settings(self, settings: Any) -> None:
        settings.UPSTREAM_ALLOWED_HOSTS = ["router.project-osrm.org"]

        container = container_from_settings()

        assert container.client._allowed_hosts == frozenset({"router.project-osrm.org"})  # noqa: SLF001

    def test_the_cache_is_the_default_django_cache(self, settings: Any) -> None:
        container = container_from_settings()

        assert container.cache._backend is caches["default"]  # noqa: SLF001

    def test_an_unknown_wind_basis_is_a_configuration_error(self, settings: Any) -> None:
        settings.RISK_WIND_BASIS = "average"

        with pytest.raises(ImproperlyConfigured, match="sustained, gust"):
            container_from_settings()

    @pytest.mark.parametrize("speed", [0, -5])
    def test_a_speed_that_is_not_positive_is_a_configuration_error(
        self, settings: Any, speed: float
    ) -> None:
        settings.TRUCK_MAX_SPEED_MPH = speed

        with pytest.raises(ImproperlyConfigured, match="TRUCK_MAX_SPEED_MPH"):
            container_from_settings()


class TestGetContainer:
    def test_it_is_built_once_and_shared(self, settings: Any) -> None:
        get_container.cache_clear()

        try:
            assert get_container() is get_container()
        finally:
            get_container.cache_clear()
