"""Checks the adapter against the real openrouteservice. Opt in: ORS_API_KEY=... pytest -m live."""

import os

import pytest

from planner.domain.models import LatLon
from planner.infra.http import UpstreamClient, default_policies
from planner.providers.routing_ors import OrsRoutingProvider

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("ORS_API_KEY"), reason="ORS_API_KEY is not set"),
]

BOULDER = LatLon(40.0150, -105.2705)
FORT_COLLINS = LatLon(40.5853, -105.0844)
WAYPOINT = LatLon(40.3, -105.15)


@pytest.fixture
def provider() -> OrsRoutingProvider:
    client = UpstreamClient(
        default_policies(), ["api.openrouteservice.org"], "WeatherAwareTruckRouting-live-check/0.1"
    )
    return OrsRoutingProvider(client, os.environ["ORS_API_KEY"])


def test_a_real_route(provider: OrsRoutingProvider) -> None:
    result = provider.routes(BOULDER, FORT_COLLINS)

    route = result.routes[0]
    assert 60_000 < route.distance_m < 120_000
    assert 1_800 < route.duration_s < 7_200
    assert len(route.segment_durations_s) == len(route.points) - 1
    assert sum(route.segment_durations_s) == pytest.approx(route.duration_s, rel=0.05)
    assert result.snap_distance_m < 1_000


def test_a_real_route_through_a_waypoint(provider: OrsRoutingProvider) -> None:
    result = provider.route_via(BOULDER, WAYPOINT, FORT_COLLINS)

    assert len(result.routes) == 1
    assert result.snap_distance_m < 1_000
