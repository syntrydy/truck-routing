"""Trying routing providers in order (SPEC section 6: routing OSRM then openrouteservice)."""

from collections.abc import Callable, Sequence

from planner.domain.models import LatLon
from planner.infra.http import UpstreamClient
from planner.providers.fallback import FALL_THROUGH, first_success
from planner.providers.protocols import RoutingProvider, RoutingResult
from planner.providers.routing_ors import OrsRoutingProvider
from planner.providers.routing_osrm import OsrmRoutingProvider

__all__ = ["FALL_THROUGH", "FallbackRoutingProvider", "build_routing_provider"]


class FallbackRoutingProvider:
    """Asks each provider in turn and returns the first result.

    The result's ``source`` names the provider that answered. If every provider fails, the
    last failure is raised.
    """

    name = "fallback"

    def __init__(self, providers: Sequence[RoutingProvider]) -> None:
        if not providers:
            msg = "at least one routing provider is required"
            raise ValueError(msg)
        self._providers = tuple(providers)

    def routes(self, origin: LatLon, destination: LatLon) -> RoutingResult:
        return self._first_success(lambda provider: provider.routes(origin, destination))

    def route_via(self, origin: LatLon, via: LatLon, destination: LatLon) -> RoutingResult:
        return self._first_success(lambda provider: provider.route_via(origin, via, destination))

    def _first_success(self, ask: Callable[[RoutingProvider], RoutingResult]) -> RoutingResult:
        return first_success(self._providers, ask)


def build_routing_provider(client: UpstreamClient, ors_api_key: str = "") -> RoutingProvider:
    """OSRM, with openrouteservice behind it when an API key is configured."""
    osrm = OsrmRoutingProvider(client)
    if not ors_api_key:
        return osrm
    return FallbackRoutingProvider([osrm, OrsRoutingProvider(client, ors_api_key)])
