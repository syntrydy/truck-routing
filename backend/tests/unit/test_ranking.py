import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from planner.domain.models import RiskLevel, RouteScore
from planner.domain.ranking import (
    Banner,
    Criterion,
    CriterionRow,
    ScoredRoute,
    rank_key,
    rank_routes,
)

HOUR = 3_600.0


def scored(  # noqa: PLR0913 - keyword-only test builder with defaults
    route_id: str,
    *,
    no_travel: float = 0.0,
    severe: float = 0.0,
    high: float = 0.0,
    avg_risk: float | None = 1.0,
    duration_s: float = HOUR,
) -> ScoredRoute:
    score = RouteScore(
        distance_mi=100.0,
        duration_s=duration_s,
        miles_by_level={
            RiskLevel.LOW: 0.0,
            RiskLevel.MODERATE: 0.0,
            RiskLevel.HIGH: high,
            RiskLevel.SEVERE: severe,
            RiskLevel.NO_TRAVEL: no_travel,
        },
        avg_risk=avg_risk,
    )
    return ScoredRoute(route_id, score)


def order(*routes: ScoredRoute) -> list[str]:
    return [route.route_id for route in rank_routes(routes).ordered]


class TestTieBreakerLevels:
    """Each level decides the order even when every later level points the other way."""

    def test_no_travel_miles_decide_first(self) -> None:
        better = scored("a", no_travel=0.0, severe=90, high=90, avg_risk=3.9, duration_s=9 * HOUR)
        worse = scored("b", no_travel=5.0, severe=0, high=0, avg_risk=0.1, duration_s=HOUR)

        result = rank_routes([worse, better])

        assert [r.route_id for r in result.ordered] == ["a", "b"]
        assert result.recommended_route_id == "a"
        assert result.reason == "Fewest No Travel miles (0.0 mi vs 5.0 mi on the next best route)"

    def test_severe_miles_decide_second(self) -> None:
        better = scored("a", severe=2.5, high=90, avg_risk=3.9, duration_s=9 * HOUR)
        worse = scored("b", severe=8.0, high=0, avg_risk=0.1, duration_s=HOUR)

        result = rank_routes([worse, better])

        assert [r.route_id for r in result.ordered] == ["a", "b"]
        assert result.reason == "Fewest Severe miles (2.5 mi vs 8.0 mi on the next best route)"

    def test_high_miles_decide_third(self) -> None:
        better = scored("a", high=10.0, avg_risk=3.9, duration_s=9 * HOUR)
        worse = scored("b", high=30.0, avg_risk=0.1, duration_s=HOUR)

        result = rank_routes([worse, better])

        assert [r.route_id for r in result.ordered] == ["a", "b"]
        assert result.reason == "Fewest High-risk miles (10.0 mi vs 30.0 mi on the next best route)"

    def test_average_risk_decides_fourth(self) -> None:
        better = scored("a", avg_risk=1.2, duration_s=9 * HOUR)
        worse = scored("b", avg_risk=1.45, duration_s=HOUR)

        result = rank_routes([worse, better])

        assert [r.route_id for r in result.ordered] == ["a", "b"]
        assert result.reason == "Lowest average risk (1.20 vs 1.45 on the next best route)"

    def test_duration_decides_last(self) -> None:
        faster = scored("a", duration_s=2 * HOUR + 10 * 60)
        slower = scored("b", duration_s=2 * HOUR + 25 * 60)

        result = rank_routes([slower, faster])

        assert [r.route_id for r in result.ordered] == ["a", "b"]
        assert result.reason == "Same risk profile and the fastest (2 h 10 min vs 2 h 25 min)"


class TestOrdering:
    def test_no_travel_outranks_severe(self) -> None:
        some_no_travel = scored("no-travel", no_travel=1.0, severe=0.0)
        lots_of_severe = scored("severe", no_travel=0.0, severe=100.0)

        assert order(some_no_travel, lots_of_severe) == ["severe", "no-travel"]

    def test_three_routes_are_fully_sorted(self) -> None:
        routes = [
            scored("slow-safe", avg_risk=1.0, duration_s=3 * HOUR),
            scored("risky", severe=10.0),
            scored("fast-safe", avg_risk=1.0, duration_s=2 * HOUR),
        ]

        assert order(*routes) == ["fast-safe", "slow-safe", "risky"]

    def test_exact_ties_keep_the_given_order(self) -> None:
        a, b = scored("a"), scored("b")

        assert order(a, b) == ["a", "b"]
        assert order(b, a) == ["b", "a"]

    def test_exact_tie_reason(self) -> None:
        assert rank_routes([scored("a"), scored("b")]).reason == (
            "Identical risk and duration to the next route"
        )

    def test_unknown_average_risk_sorts_after_a_known_one(self) -> None:
        unknown = scored("unknown", avg_risk=None)
        known = scored("known", avg_risk=3.0)

        result = rank_routes([unknown, known])

        assert [r.route_id for r in result.ordered] == ["known", "unknown"]
        assert result.reason == "Lowest average risk (3.00 vs unknown on the next best route)"


class TestRounding:
    def test_float_noise_in_no_travel_miles_falls_through_to_severe(self) -> None:
        noisy = scored("noisy", no_travel=1e-12, severe=0.0)
        clean = scored("clean", no_travel=0.0, severe=5.0)

        result = rank_routes([clean, noisy])

        assert [r.route_id for r in result.ordered] == ["noisy", "clean"]
        assert result.recommended_route_id == "noisy"
        assert result.banner is None
        assert result.reason is not None
        assert result.reason.startswith("Fewest Severe miles")

    def test_miles_within_a_rounding_step_tie_and_fall_through(self) -> None:
        a = scored("a", high=10.04, avg_risk=1.0)
        b = scored("b", high=10.00, avg_risk=2.0)

        assert order(b, a) == ["a", "b"]

    def test_miles_a_rounding_step_apart_do_not_tie(self) -> None:
        a = scored("a", high=10.06, avg_risk=1.0)
        b = scored("b", high=10.00, avg_risk=2.0)

        assert order(a, b) == ["b", "a"]

    def test_average_risk_noise_falls_through_to_duration(self) -> None:
        noisier_but_faster = scored("a", avg_risk=1.0000001, duration_s=2 * HOUR)
        cleaner_but_slower = scored("b", avg_risk=1.0, duration_s=3 * HOUR)

        assert order(cleaner_but_slower, noisier_but_faster) == ["a", "b"]

    def test_average_risk_a_hundredth_apart_does_not_tie(self) -> None:
        a = scored("a", avg_risk=1.02, duration_s=HOUR)
        b = scored("b", avg_risk=1.00, duration_s=9 * HOUR)

        assert order(a, b) == ["b", "a"]


class TestNoSafeRoute:
    def test_every_route_with_no_travel_miles_gives_no_recommendation(self) -> None:
        result = rank_routes([scored("a", no_travel=12.0), scored("b", no_travel=4.0)])

        assert result.recommended_route_id is None
        assert result.reason is None
        assert result.banner is Banner.NO_SAFE_ROUTE

    def test_routes_are_still_ranked_when_there_is_no_recommendation(self) -> None:
        result = rank_routes([scored("a", no_travel=12.0), scored("b", no_travel=4.0)])

        assert [r.route_id for r in result.ordered] == ["b", "a"]

    def test_a_single_route_with_no_travel_miles(self) -> None:
        result = rank_routes([scored("only", no_travel=3.0)])

        assert result.recommended_route_id is None
        assert result.banner is Banner.NO_SAFE_ROUTE

    def test_one_clean_route_is_enough_to_recommend(self) -> None:
        result = rank_routes([scored("bad", no_travel=9.0), scored("good")])

        assert result.recommended_route_id == "good"
        assert result.banner is None

    def test_banner_value(self) -> None:
        assert Banner.NO_SAFE_ROUTE == "NO_SAFE_ROUTE"


class TestSingleRoute:
    def test_single_route_is_recommended_with_its_own_reason(self) -> None:
        result = rank_routes([scored("only")])

        assert result.recommended_route_id == "only"
        assert result.reason == "Only one route is available"
        assert result.banner is None

    def test_rejects_an_empty_list(self) -> None:
        with pytest.raises(ValueError, match="no routes"):
            rank_routes([])


class TestDurationWording:
    def test_under_an_hour_shows_minutes_only(self) -> None:
        result = rank_routes([scored("a", duration_s=45 * 60), scored("b", duration_s=50 * 60)])

        assert result.reason == "Same risk profile and the fastest (45 min vs 50 min)"

    def test_seconds_are_added_when_the_minutes_would_look_equal(self) -> None:
        result = rank_routes([scored("a", duration_s=HOUR), scored("b", duration_s=HOUR + 20)])

        assert result.reason == (
            "Same risk profile and the fastest (1 h 0 min 0 s vs 1 h 0 min 20 s)"
        )


class TestRankKey:
    def test_missing_levels_count_as_zero_miles(self) -> None:
        score = RouteScore(distance_mi=10.0, duration_s=60.0, avg_risk=0.5)

        assert rank_key(score) == (0.0, 0.0, 0.0, 0.5, 60.0)

    def test_unknown_average_risk_becomes_infinity(self) -> None:
        score = RouteScore(distance_mi=10.0, duration_s=60.0, avg_risk=None)

        assert math.isinf(rank_key(score).avg_risk)


route_strategy = st.builds(
    scored,
    st.text(alphabet="abcdefgh", min_size=1, max_size=3),
    no_travel=st.sampled_from([0.0, 0.0, 1.0, 5.0]),
    severe=st.sampled_from([0.0, 2.0, 7.5]),
    high=st.sampled_from([0.0, 3.0, 12.0]),
    avg_risk=st.sampled_from([None, 0.5, 1.0, 2.5]),
    duration_s=st.sampled_from([HOUR, 2 * HOUR, 3 * HOUR]),
)


@given(
    st.lists(route_strategy, min_size=1, max_size=6).flatmap(
        lambda routes: st.tuples(st.just(routes), st.permutations(routes))
    )
)
def test_ranking_is_sorted_and_independent_of_input_order(
    routes_and_shuffle: tuple[list[ScoredRoute], list[ScoredRoute]],
) -> None:
    routes, shuffled = routes_and_shuffle

    first = rank_routes(routes)
    second = rank_routes(shuffled)
    keys = [rank_key(route.score) for route in first.ordered]

    assert keys == sorted(keys)
    assert keys == [rank_key(route.score) for route in second.ordered]
    if first.recommended_route_id is None:
        assert keys[0].no_travel_mi > 0
        assert first.banner is Banner.NO_SAFE_ROUTE
    else:
        assert first.recommended_route_id == first.ordered[0].route_id
        assert keys[0].no_travel_mi == 0


class TestBreakdown:
    """The criteria in ranking order, each route's value, and where the decision was made."""

    def rows(self, *routes: ScoredRoute) -> dict[Criterion, CriterionRow]:
        return {row.criterion: row for row in rank_routes(routes).breakdown.rows}

    def test_the_criteria_come_in_the_order_the_ranking_uses_them(self) -> None:
        breakdown = rank_routes([scored("a"), scored("b")]).breakdown

        assert [row.criterion for row in breakdown.rows] == [
            Criterion.NO_TRAVEL_MI,
            Criterion.SEVERE_MI,
            Criterion.HIGH_MI,
            Criterion.AVG_RISK,
            Criterion.DURATION,
        ]

    def test_values_are_in_the_order_of_the_ranked_routes(self) -> None:
        worse = scored("b", severe=8.0, avg_risk=2.0, duration_s=2 * HOUR)
        better = scored("a", severe=2.5, avg_risk=1.0, duration_s=3 * HOUR)

        breakdown = rank_routes([worse, better]).breakdown

        assert breakdown.route_ids == ("a", "b")
        severe = next(row for row in breakdown.rows if row.criterion is Criterion.SEVERE_MI)
        assert severe.values == (2.5, 8.0)
        assert severe.best == (True, False)

    @pytest.mark.parametrize(
        ("better", "worse", "decisive"),
        [
            ({"no_travel": 0.0}, {"no_travel": 5.0}, Criterion.NO_TRAVEL_MI),
            ({"severe": 2.5}, {"severe": 8.0}, Criterion.SEVERE_MI),
            ({"high": 2.5}, {"high": 8.0}, Criterion.HIGH_MI),
            ({"avg_risk": 0.5}, {"avg_risk": 1.5}, Criterion.AVG_RISK),
            ({"duration_s": HOUR}, {"duration_s": 2 * HOUR}, Criterion.DURATION),
        ],
    )
    def test_the_decisive_row_is_the_first_where_the_best_two_differ(
        self, better: dict[str, float], worse: dict[str, float], decisive: Criterion
    ) -> None:
        result = rank_routes([scored("b", **worse), scored("a", **better)])

        marked = [row.criterion for row in result.breakdown.rows if row.decisive]
        assert marked == [decisive]

    def test_the_decisive_row_names_the_same_criterion_as_the_reason(self) -> None:
        result = rank_routes([scored("b", high=8.0), scored("a", high=2.5)])

        assert result.reason is not None
        assert result.reason.startswith("Fewest High-risk miles")
        assert [r.criterion for r in result.breakdown.rows if r.decisive] == [Criterion.HIGH_MI]

    def test_a_criterion_after_the_decision_is_not_marked_even_if_it_differs(self) -> None:
        better = scored("a", severe=1.0, avg_risk=3.0)
        worse = scored("b", severe=9.0, avg_risk=0.5)

        rows = self.rows(better, worse)

        assert rows[Criterion.SEVERE_MI].decisive
        assert not rows[Criterion.AVG_RISK].decisive

    def test_nothing_is_decisive_for_identical_routes(self) -> None:
        breakdown = rank_routes([scored("a"), scored("b")]).breakdown

        assert not any(row.decisive for row in breakdown.rows)
        assert all(all(row.best) for row in breakdown.rows)

    def test_a_single_route_has_nothing_to_decide(self) -> None:
        breakdown = rank_routes([scored("a")]).breakdown

        assert breakdown.route_ids == ("a",)
        assert not any(row.decisive for row in breakdown.rows)

    def test_an_unknown_average_risk_is_none_and_never_best(self) -> None:
        rows = self.rows(scored("a", avg_risk=None), scored("b", avg_risk=3.0))

        row = rows[Criterion.AVG_RISK]
        assert row.values == (3.0, None)
        assert row.best == (True, False)

    def test_values_are_the_rounded_ones_the_ranking_compared(self) -> None:
        rows = self.rows(scored("a", severe=2.04, avg_risk=1.004), scored("b", severe=2.04))

        assert rows[Criterion.SEVERE_MI].values == (2.0, 2.0)
        assert rows[Criterion.AVG_RISK].values == (1.0, 1.0)

    def test_there_is_a_breakdown_when_no_route_is_safe(self) -> None:
        result = rank_routes([scored("a", no_travel=9.0), scored("b", no_travel=3.0)])

        assert result.recommended_route_id is None
        assert result.breakdown.route_ids == ("b", "a")
        assert [r.criterion for r in result.breakdown.rows if r.decisive] == [
            Criterion.NO_TRAVEL_MI
        ]
