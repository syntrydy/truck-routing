import json
import logging
from typing import Any

import pytest

from planner.infra.metrics import record_cache_lookup, record_upstream_call
from planner.infra.resilience import BreakerState
from planner.services.models import TooClose
from planner.services.observed import ObservedPlanService
from tests.infra.fakes import FakeClock
from tests.services.stubs import StubRouting, StubWeather
from tests.services.test_plan import make_service, request_for, three_routes


class Scripted:
    """Stands in for the plan service: records metrics like the real providers do."""

    def __init__(self, inner: Any, clock: FakeClock, fail: Exception | None = None) -> None:
        self.inner, self.clock, self.fail = inner, clock, fail

    def plan(self, request: Any) -> Any:  # noqa: ANN401
        record_upstream_call("osrm", 0.25)
        record_upstream_call("open-meteo", 0.5)
        record_cache_lookup(hit=True)
        record_cache_lookup(hit=False)
        self.clock.advance(1.5)
        if self.fail:
            raise self.fail
        return self.inner.plan(request)


def plan_records(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    return [r.plan for r in caplog.records if hasattr(r, "plan")]


@pytest.fixture
def setup(caplog: pytest.LogCaptureFixture) -> Any:  # noqa: ANN401
    caplog.set_level(logging.INFO, logger="planner.services.observed")
    routes = three_routes()
    clock = FakeClock()
    inner = make_service(StubRouting(routes), StubWeather(), clock)
    states = {"osrm": BreakerState.CLOSED, "open-meteo": BreakerState.OPEN}

    def build(fail: Exception | None = None) -> ObservedPlanService:
        return ObservedPlanService(
            Scripted(inner, clock, fail),  # type: ignore[arg-type]
            lambda: states,
            monotonic=clock,
        )

    return build, request_for(routes[0]), inner


class TestObservedPlanService:
    def test_it_returns_what_the_service_returns(self, setup: Any) -> None:
        build, request, inner = setup

        assert build().plan(request).routes == inner.plan(request).routes

    def test_one_record_per_plan_with_the_agreed_metrics(
        self, setup: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        build, request, _ = setup

        result = build().plan(request)

        (record,) = plan_records(caplog)
        assert record["outcome"] == "ok"
        assert record["duration_ms"] == 1500
        assert record["route_count"] == len(result.routes) == 3
        assert record["checkpoint_count"] == sum(len(r.checkpoints) for r in result.routes)
        assert record["distance_mi"] == round(result.routes[0].distance_mi, 1)
        assert record["cache_hit_ratio"] == 0.5
        assert record["upstream"] == {
            "open-meteo": {"calls": 1, "ms": 500},
            "osrm": {"calls": 1, "ms": 250},
        }
        assert record["breakers"] == {"osrm": "closed", "open-meteo": "open"}
        assert "weather_points" in record

    def test_the_record_is_json_and_holds_no_coordinates_or_labels(
        self, setup: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        build, request, _ = setup

        build().plan(request)

        (record,) = plan_records(caplog)
        text = json.dumps(record)
        assert str(request.origin.lat)[:6] not in text
        assert "label" not in text

    def test_a_failed_plan_is_logged_with_its_error_and_raised_again(
        self, setup: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        build, request, _ = setup

        with pytest.raises(TooClose):
            build(TooClose("near")).plan(request)

        (record,) = plan_records(caplog)
        assert record["outcome"] == "TooClose"
        assert record["duration_ms"] == 1500
        assert "route_count" not in record

    def test_without_cache_lookups_the_ratio_is_null(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO, logger="planner.services.observed")
        routes = three_routes()
        service = ObservedPlanService(make_service(StubRouting(routes), StubWeather()), lambda: {})

        service.plan(request_for(routes[0]))

        (record,) = plan_records(caplog)
        assert record["cache_hit_ratio"] is None
        assert record["upstream"] == {}
