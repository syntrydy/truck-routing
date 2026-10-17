import pytest
from hypothesis import given
from hypothesis import strategies as st

from planner.domain.models import RiskLevel, is_known, max_known

KNOWN_LEVELS = [
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
]


class TestRiskLevel:
    def test_known_levels_are_ordered_from_low_to_no_travel(self) -> None:
        assert sorted(KNOWN_LEVELS) == KNOWN_LEVELS
        assert [int(level) for level in KNOWN_LEVELS] == [0, 1, 2, 3, 4]

    @pytest.mark.parametrize(
        ("lower", "higher"),
        [
            (RiskLevel.LOW, RiskLevel.MODERATE),
            (RiskLevel.MODERATE, RiskLevel.HIGH),
            (RiskLevel.HIGH, RiskLevel.SEVERE),
            (RiskLevel.SEVERE, RiskLevel.NO_TRAVEL),
        ],
    )
    def test_each_level_ranks_below_the_next(self, lower: RiskLevel, higher: RiskLevel) -> None:
        assert lower < higher

    def test_unknown_uses_the_wire_value_minus_one(self) -> None:
        assert int(RiskLevel.UNKNOWN) == -1


class TestIsKnown:
    @pytest.mark.parametrize("level", KNOWN_LEVELS)
    def test_real_levels_are_known(self, level: RiskLevel) -> None:
        assert is_known(level)

    def test_unknown_is_not_known(self) -> None:
        assert not is_known(RiskLevel.UNKNOWN)


class TestMaxKnown:
    def test_returns_highest_level(self) -> None:
        assert max_known([RiskLevel.LOW, RiskLevel.HIGH, RiskLevel.MODERATE]) is RiskLevel.HIGH

    def test_ignores_unknown_among_known_levels(self) -> None:
        assert max_known([RiskLevel.UNKNOWN, RiskLevel.LOW]) is RiskLevel.LOW

    def test_unknown_is_never_reported_as_low(self) -> None:
        assert max_known([RiskLevel.UNKNOWN, RiskLevel.UNKNOWN]) is RiskLevel.UNKNOWN

    def test_empty_input_is_unknown(self) -> None:
        assert max_known([]) is RiskLevel.UNKNOWN

    def test_accepts_any_iterable(self) -> None:
        assert max_known(level for level in KNOWN_LEVELS) is RiskLevel.NO_TRAVEL

    @given(st.lists(st.sampled_from([*KNOWN_LEVELS, RiskLevel.UNKNOWN])))
    def test_equals_maximum_of_known_levels(self, levels: list[RiskLevel]) -> None:
        known = [level for level in levels if level is not RiskLevel.UNKNOWN]
        expected = max(known) if known else RiskLevel.UNKNOWN
        assert max_known(levels) is expected
