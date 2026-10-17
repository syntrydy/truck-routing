"""Reports what each plan did: one structured log record per plan (SPEC section 9)."""

import logging
from collections.abc import Callable, Mapping
from time import monotonic as default_monotonic
from typing import Any

from planner.infra.metrics import RequestMetrics, metrics_scope
from planner.infra.resilience import BreakerState
from planner.services.models import PlanRequest, PlanResult
from planner.services.plan import PlanService

logger = logging.getLogger(__name__)

MILES_DECIMALS = 1
MILLISECONDS = 1000
RATIO_DECIMALS = 2


class ObservedPlanService:
    """A ``PlanService`` that logs the distance, size, cache use, upstream time, breaker
    states and total duration of every plan, whether it succeeds or fails.

    The record holds numbers and names only: no coordinates, labels or addresses.
    """

    def __init__(
        self,
        service: PlanService,
        breaker_states: Callable[[], Mapping[str, BreakerState]],
        monotonic: Callable[[], float] = default_monotonic,
    ) -> None:
        self._service = service
        self._breaker_states = breaker_states
        self._monotonic = monotonic

    @property
    def service(self) -> PlanService:
        """The service being observed."""
        return self._service

    def plan(self, request: PlanRequest) -> PlanResult:
        """Plan ``request`` exactly as the wrapped service does, and log how it went."""
        started = self._monotonic()
        outcome = "ok"
        result: PlanResult | None = None
        with metrics_scope() as metrics:
            try:
                result = self._service.plan(request)
            except Exception as error:
                outcome = type(error).__name__
                raise
            finally:
                self._log(outcome, result, metrics, self._monotonic() - started)
        return result

    def _log(
        self, outcome: str, result: PlanResult | None, metrics: RequestMetrics, duration_s: float
    ) -> None:
        summary: dict[str, Any] = {
            "outcome": outcome,
            "duration_ms": round(duration_s * MILLISECONDS),
            "weather_points": metrics.weather_points,
            "cache_hit_ratio": _ratio(metrics.cache_hit_ratio),
            "upstream": {
                provider: {"calls": usage.calls, "ms": round(usage.seconds * MILLISECONDS)}
                for provider, usage in metrics.upstream.items()
            },
            "breakers": {name: state.value for name, state in self._breaker_states().items()},
        }
        if result is not None:
            summary |= {
                "route_count": len(result.routes),
                "checkpoint_count": sum(len(route.checkpoints) for route in result.routes),
                "distance_mi": round(result.routes[0].distance_mi, MILES_DECIMALS)
                if result.routes
                else None,
            }
        logger.info("plan %s", outcome, extra={"plan": summary})


def _ratio(value: float | None) -> float | None:
    return None if value is None else round(value, RATIO_DECIMALS)
