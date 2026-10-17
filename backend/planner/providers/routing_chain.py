"""Trying routing providers in order (SPEC section 6: routing OSRM then openrouteservice)."""

import logging
from collections.abc import Callable, Sequence

from planner.domain.models import LatLon
from planner.infra.errors import UpstreamContractError, UpstreamTimeout, UpstreamUnavailable
from planner.infra.http import UpstreamClient
from planner.providers.protocols import RoutingProvider, RoutingResult
from planner.providers.routing_ors import OrsRoutingProvider
from planner.providers.routing_osrm import OsrmRoutingProvider

logger = logging.getLogger(__name__)

# A provider that is down, too slow or answering nonsense is replaced by the next one.
# NoRoute is an answer, not a failure, and other rejections would be rejected again.
FALL_THROUGH = (UpstreamUnavailable, UpstreamTimeout, UpstreamContractError)


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
        failures: list[Exception] = []
        for provider in self._providers:
            try:
                return ask(provider)
            except FALL_THROUGH as error:
                logger.warning(
                    "routing provider %s failed (%s)", provider.name, type(error).__name__
                )
                failures.append(error)
        raise failures[-1]


def build_routing_provider(client: UpstreamClient, ors_api_key: str = "") -> RoutingProvider:
    """OSRM, with openrouteservice behind it when an API key is configured."""
    osrm = OsrmRoutingProvider(client)
    if not ors_api_key:
        return osrm
    return FallbackRoutingProvider([osrm, OrsRoutingProvider(client, ors_api_key)])
