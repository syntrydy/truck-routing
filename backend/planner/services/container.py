"""Builds the object graph from settings, once (SPEC section 3.1: dependency injection)."""

from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.base import BaseCache
from django.core.exceptions import ImproperlyConfigured

from planner.domain.risk import WindBasis
from planner.infra.cache import StaleIfErrorCache
from planner.infra.fixture_http import FixtureUpstream
from planner.infra.http import UpstreamClient, upstream_client_from_settings
from planner.providers.geocode_chain import build_geocoder
from planner.providers.protocols import GeocodeProvider
from planner.providers.routing_chain import build_routing_provider
from planner.providers.weather_openmeteo import OpenMeteoWeatherProvider
from planner.services.observed import ObservedPlanService
from planner.services.plan import PlanService


@dataclass(frozen=True, slots=True)
class Container:
    """What the views need: the plan service and the geocoder, with their shared parts."""

    plan_service: ObservedPlanService
    geocoder: GeocodeProvider
    client: UpstreamClient
    cache: StaleIfErrorCache


def build_container(
    *,
    client: UpstreamClient,
    cache_backend: BaseCache,
    ors_api_key: str,
    max_speed_mph: float,
    wind_basis: WindBasis,
) -> Container:
    """Wire the providers, the cache and the plan service from explicit parts."""
    cache = StaleIfErrorCache(cache_backend)
    return Container(
        plan_service=ObservedPlanService(
            PlanService(
                build_routing_provider(client, ors_api_key),
                OpenMeteoWeatherProvider(client, cache),
                max_speed_mph=max_speed_mph,
                wind_basis=wind_basis,
            ),
            client.breaker_states,
        ),
        geocoder=build_geocoder(client, cache),
        client=client,
        cache=cache,
    )


def container_from_settings() -> Container:
    """Build the container from Django settings (``ORS_API_KEY`` and friends)."""
    try:
        wind_basis = WindBasis(settings.RISK_WIND_BASIS)
    except ValueError as error:
        allowed = ", ".join(basis.value for basis in WindBasis)
        msg = f"RISK_WIND_BASIS must be one of: {allowed}"
        raise ImproperlyConfigured(msg) from error
    if settings.TRUCK_MAX_SPEED_MPH <= 0:
        msg = "TRUCK_MAX_SPEED_MPH must be positive"
        raise ImproperlyConfigured(msg)
    recorded = (
        FixtureUpstream(settings.FIXTURES_DIR).client()
        if settings.PROVIDERS_MODE == "fixtures"
        else None
    )
    return build_container(
        client=upstream_client_from_settings(recorded),
        cache_backend=caches["default"],
        ors_api_key=settings.ORS_API_KEY,
        max_speed_mph=settings.TRUCK_MAX_SPEED_MPH,
        wind_basis=wind_basis,
    )


@lru_cache(maxsize=1)
def get_container() -> Container:
    """The process-wide container, built on first use."""
    return container_from_settings()
