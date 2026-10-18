"""The stormy demo plans through the real service and shows the risk rules at work."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from planner.domain.models import RiskLevel
from planner.domain.risk import WindBasis
from planner.providers.recorded import SOURCE, load_scenario
from planner.services.demo import DemoPlanner
from planner.services.models import PlanResult

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "demo"
DANGEROUS = {RiskLevel.HIGH, RiskLevel.SEVERE, RiskLevel.NO_TRAVEL}
HEAVY_LB = 42_000
LIGHT_LB = 20_000


def demo_at(now: datetime) -> DemoPlanner:
    return DemoPlanner(
        load_scenario(FIXTURES), max_speed_mph=65.0, wind_basis=WindBasis.SUSTAINED, now=lambda: now
    )


def worst_levels(result: PlanResult) -> dict[str, RiskLevel]:
    return {
        route.label: max(c.level for c in route.checkpoints if c.level is not RiskLevel.UNKNOWN)
        for route in result.routes
    }


NOW = datetime(2026, 10, 18, 14, 20, tzinfo=UTC)


class TestTheDemoPlan:
    def test_it_is_a_plan_from_the_demo_providers_with_three_routes(self) -> None:
        result = demo_at(NOW).plan(HEAVY_LB, 25)

        assert len(result.routes) == 3
        assert result.meta.routing_source == SOURCE
        assert result.meta.weather_source == SOURCE
        assert result.banner is None

    def test_the_storm_makes_a_heavy_load_dangerous_on_some_route_and_not_on_another(self) -> None:
        worst = worst_levels(demo_at(NOW).plan(HEAVY_LB, 25))

        assert DANGEROUS & set(worst.values())
        assert len(set(worst.values())) > 1

    def test_the_fastest_road_runs_into_the_storm_and_gets_no_travel(self) -> None:
        result = demo_at(NOW).plan(HEAVY_LB, 25)

        fastest = min(result.routes, key=lambda route: route.duration_s)

        assert worst_levels(result)[fastest.label] is RiskLevel.NO_TRAVEL
        assert result.recommended_route_id != fastest.id

    def test_the_recommended_route_is_not_the_most_dangerous_one(self) -> None:
        result = demo_at(NOW).plan(HEAVY_LB, 25)
        worst = worst_levels(result)
        recommended = next(r.label for r in result.routes if r.id == result.recommended_route_id)

        assert worst[recommended] < max(worst.values())

    def test_a_heavier_load_is_worse_in_the_same_storm(self) -> None:
        light = worst_levels(demo_at(NOW).plan(LIGHT_LB, 25))
        heavy = worst_levels(demo_at(NOW).plan(HEAVY_LB, 25))

        assert max(heavy.values()) > max(light.values())

    @pytest.mark.parametrize("hour", [0, 6, 13, 23])
    def test_the_storm_follows_the_departure_whatever_the_hour(self, hour: int) -> None:
        reference = worst_levels(demo_at(NOW).plan(HEAVY_LB, 25))

        result = demo_at(datetime(2026, 11, 3, hour, NOW.minute, tzinfo=UTC)).plan(HEAVY_LB, 25)

        assert worst_levels(result) == reference
