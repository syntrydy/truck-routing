"""The stormy demo: the real plan service, on a recorded corridor and a recorded storm.

Only the two providers are replaced (SPEC section 10); routes, checkpoints, risk, load rules,
ranking and the heatmap are the live code, so a demo shows the rules at work.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from planner.domain.risk import WindBasis
from planner.providers.recorded import (
    DEMO_DESTINATION,
    DEMO_ORIGIN,
    DemoScenario,
    RecordedRouting,
    RecordedWeather,
    load_scenario,
)
from planner.services.models import PlanRequest, PlanResult
from planner.services.plan import PlanService

DEMO_DIR = "demo"


class DemoPlanner:
    """Plans the recorded Denver to Salt Lake City trip, leaving now."""

    def __init__(
        self,
        scenario: DemoScenario,
        *,
        max_speed_mph: float,
        wind_basis: WindBasis,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._scenario = scenario
        self._max_speed_mph = max_speed_mph
        self._wind_basis = wind_basis
        self._now = now

    def plan(self, load_lb: int, interval_mi: int) -> PlanResult:
        """The demo trip for a load in pounds and a checkpoint spacing in miles."""
        departure = self._now()
        departure_hour = departure.replace(minute=0, second=0, microsecond=0)
        service = PlanService(
            RecordedRouting(self._scenario),
            RecordedWeather(self._scenario, departure_hour),
            max_speed_mph=self._max_speed_mph,
            wind_basis=self._wind_basis,
            now=self._now,
        )
        return service.plan(
            PlanRequest(
                origin=DEMO_ORIGIN,
                destination=DEMO_DESTINATION,
                departure=departure,
                load_lb=load_lb,
                interval_mi=interval_mi,
            )
        )


@lru_cache(maxsize=1)
def get_demo_planner() -> DemoPlanner:
    """The process-wide demo planner, built from the settings on first use."""
    try:
        wind_basis = WindBasis(settings.RISK_WIND_BASIS)
    except ValueError as error:
        msg = "RISK_WIND_BASIS is not a wind basis"
        raise ImproperlyConfigured(msg) from error
    scenario = load_scenario(Path(settings.FIXTURES_DIR) / DEMO_DIR)
    return DemoPlanner(scenario, max_speed_mph=settings.TRUCK_MAX_SPEED_MPH, wind_basis=wind_basis)
