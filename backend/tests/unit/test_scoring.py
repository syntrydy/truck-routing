from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from planner.domain.models import Checkpoint, LatLon, RiskLevel
from planner.domain.scoring import build_stretches, score_route

LOW = RiskLevel.LOW
MODERATE = RiskLevel.MODERATE
HIGH = RiskLevel.HIGH
SEVERE = RiskLevel.SEVERE
NO_TRAVEL = RiskLevel.NO_TRAVEL
UNKNOWN = RiskLevel.UNKNOWN
DEPARTURE = datetime(2026, 1, 15, 8, tzinfo=UTC)


def route(*stops: tuple[float, RiskLevel]) -> list[Checkpoint]:
    """Checkpoints at the given (mile, level) pairs, one hour apart."""
    return [
        Checkpoint(
            index=index,
            location=LatLon(0.0, 0.0),
            distance_mi=miles,
            eta=DEPARTURE + timedelta(hours=index),
            level=level,
        )
        for index, (miles, level) in enumerate(stops)
    ]


class TestBuildStretches:
    def test_stretch_level_is_the_worse_of_its_two_ends(self) -> None:
        checkpoints = route((0, LOW), (25, HIGH), (50, MODERATE), (60, LOW))

        stretches = build_stretches(checkpoints)

        assert [s.level for s in stretches] == [HIGH, HIGH, MODERATE]
        assert [s.length_mi for s in stretches] == [25, 25, 10]
        assert [(s.start_index, s.end_index) for s in stretches] == [(0, 1), (1, 2), (2, 3)]

    def test_unknown_end_with_a_milder_end_makes_the_stretch_unknown(self) -> None:
        stretches = build_stretches(route((0, LOW), (10, UNKNOWN), (20, HIGH)))

        assert [s.level for s in stretches] == [UNKNOWN, UNKNOWN]

    @pytest.mark.parametrize("known", [SEVERE, NO_TRAVEL])
    def test_unknown_end_does_not_hide_a_severe_end(self, known: RiskLevel) -> None:
        stretches = build_stretches(route((0, UNKNOWN), (10, known)))

        assert [s.level for s in stretches] == [known]

    def test_single_checkpoint_has_no_stretches(self) -> None:
        assert build_stretches(route((0, LOW))) == []


class TestScoreRoute:
    def test_known_route_matches_hand_computed_figures(self) -> None:
        checkpoints = route((0, LOW), (25, HIGH), (50, MODERATE), (60, LOW))

        score = score_route(checkpoints, duration_s=4_000.0)

        assert score.distance_mi == 60
        assert score.duration_s == 4_000.0
        assert score.miles_by_level == {
            LOW: 0.0,
            MODERATE: 10.0,
            HIGH: 50.0,
            SEVERE: 0.0,
            NO_TRAVEL: 0.0,
        }
        assert score.unknown_miles == 0.0
        assert score.avg_risk == pytest.approx((2 * 50 + 1 * 10) / 60)
        assert score.worst_level is HIGH
        assert not score.low_confidence

    def test_unknown_miles_are_excluded_from_the_average_and_never_counted_as_low(self) -> None:
        checkpoints = route((0, LOW), (10, UNKNOWN), (20, LOW), (30, SEVERE))

        score = score_route(checkpoints, duration_s=1_800.0)

        assert score.unknown_miles == 20
        assert score.miles_by_level[LOW] == 0.0
        assert score.miles_by_level[SEVERE] == 10
        assert score.avg_risk == 3.0
        assert score.worst_level is SEVERE
        assert score.low_confidence

    def test_unknown_next_to_severe_still_counts_as_severe_miles(self) -> None:
        score = score_route(route((0, SEVERE), (10, UNKNOWN)), duration_s=600.0)

        assert score.miles_by_level[SEVERE] == 10
        assert score.unknown_miles == 0.0

    def test_route_with_no_known_stretch(self) -> None:
        score = score_route(route((0, UNKNOWN), (10, UNKNOWN), (20, UNKNOWN)), 1_200.0)

        assert score.unknown_miles == 20
        assert all(miles == 0.0 for miles in score.miles_by_level.values())
        assert score.avg_risk is None
        assert score.worst_level is UNKNOWN
        assert score.low_confidence

    def test_worst_level_is_taken_from_the_known_stretches(self) -> None:
        score = score_route(route((0, HIGH), (10, HIGH), (20, UNKNOWN)), 1_200.0)

        assert score.worst_level is HIGH
        assert score.unknown_miles == 10
        assert score.miles_by_level[HIGH] == 10

    def test_no_travel_miles_are_tracked_separately(self) -> None:
        score = score_route(route((0, LOW), (15, NO_TRAVEL), (40, LOW)), 3_000.0)

        assert score.miles_by_level[NO_TRAVEL] == 40
        assert score.worst_level is NO_TRAVEL
        assert score.avg_risk == 4.0

    def test_every_known_level_is_present_even_when_unused(self) -> None:
        score = score_route(route((0, LOW), (10, LOW)), 600.0)

        assert set(score.miles_by_level) == {LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL}

    @pytest.mark.parametrize(
        ("unknown_end_mi", "expected"),
        [(20.0, False), (20.1, True), (19.9, False)],
    )
    def test_low_confidence_needs_strictly_more_than_20_percent_unknown(
        self, unknown_end_mi: float, expected: bool
    ) -> None:
        checkpoints = route((0, UNKNOWN), (unknown_end_mi, LOW), (100, LOW))

        score = score_route(checkpoints, duration_s=6_000.0)

        assert score.unknown_miles == unknown_end_mi
        assert score.low_confidence is expected

    def test_one_missing_checkpoint_on_a_100_mile_trip_is_exactly_at_the_threshold(self) -> None:
        stops = [(float(mile), LOW) for mile in range(0, 101, 10)]
        stops[5] = (50.0, UNKNOWN)

        score = score_route(route(*stops), duration_s=6_000.0)

        assert score.unknown_miles == 20  # the two stretches touching the missing checkpoint
        assert not score.low_confidence

    def test_two_missing_checkpoints_tip_the_route_into_low_confidence(self) -> None:
        stops = [(float(mile), LOW) for mile in range(0, 101, 10)]
        stops[3] = (30.0, UNKNOWN)
        stops[7] = (70.0, UNKNOWN)

        score = score_route(route(*stops), duration_s=6_000.0)

        assert score.unknown_miles == 40
        assert score.low_confidence

    def test_rejects_a_single_checkpoint(self) -> None:
        with pytest.raises(ValueError, match="two checkpoints"):
            score_route(route((0, LOW)), 0.0)

    def test_rejects_a_route_without_length(self) -> None:
        with pytest.raises(ValueError, match="no length"):
            score_route(route((5, LOW), (5, LOW)), 0.0)


levels = st.sampled_from([LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL, UNKNOWN])


@given(
    st.lists(
        st.tuples(st.floats(min_value=0.5, max_value=50), levels),
        min_size=1,
        max_size=30,
    ),
    levels,
)
def test_score_invariants(steps: list[tuple[float, RiskLevel]], first_level: RiskLevel) -> None:
    stops = [(0.0, first_level)]
    for length, level in steps:
        stops.append((stops[-1][0] + length, level))
    checkpoints = route(*stops)
    known_levels = [s.level for s in build_stretches(checkpoints) if s.level is not UNKNOWN]

    score = score_route(checkpoints, duration_s=1.0)

    assert sum(score.miles_by_level.values()) + score.unknown_miles == pytest.approx(
        score.distance_mi
    )
    assert score.unknown_miles >= 0
    if known_levels:
        assert score.avg_risk is not None
        assert min(known_levels) - 1e-9 <= score.avg_risk <= max(known_levels) + 1e-9
        assert score.worst_level is max(known_levels)
    else:
        assert score.avg_risk is None
        assert score.worst_level is UNKNOWN
    assert score.low_confidence == (score.unknown_miles / score.distance_mi > 0.20)
