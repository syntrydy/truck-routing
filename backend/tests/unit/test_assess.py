import pytest
from hypothesis import given
from hypothesis import strategies as st

from planner.domain.models import RiskLevel, WeatherSample
from planner.domain.risk import Factor, WindBasis, assess

LOW = RiskLevel.LOW
MODERATE = RiskLevel.MODERATE
HIGH = RiskLevel.HIGH
SEVERE = RiskLevel.SEVERE
NO_TRAVEL = RiskLevel.NO_TRAVEL
UNKNOWN = RiskLevel.UNKNOWN


def calm(**overrides: float | None) -> WeatherSample:
    """A fully known, calm sample with selected fields overridden."""
    values: dict[str, float | None] = {
        "wind_mph": 0.0,
        "gust_mph": 0.0,
        "rain_in_hr": 0.0,
        "snow_in_hr": 0.0,
    }
    values.update(overrides)
    return WeatherSample(**values)  # type: ignore[arg-type]


class TestLoadRules:
    @pytest.mark.parametrize(
        ("wind_mph", "load_lb", "expected"),
        [
            (47.0, 0, SEVERE),
            (47.0, 30_000, SEVERE),
            (47.0, 30_001, NO_TRAVEL),
            (45.0, 30_000, SEVERE),
            (45.0, 30_001, NO_TRAVEL),
            (54.99, 30_001, NO_TRAVEL),
            (44.99, 30_001, HIGH),
            (40.0, 40_000, HIGH),
            (40.0, 40_001, SEVERE),
            (35.0, 40_001, SEVERE),
            (44.99, 40_001, SEVERE),
            (34.99, 100_000, MODERATE),
            (55.0, 0, NO_TRAVEL),
            (60.0, 0, NO_TRAVEL),
            (10.0, 100_000, LOW),
        ],
    )
    def test_checkpoint_level_by_wind_and_load(
        self, wind_mph: float, load_lb: float, expected: RiskLevel
    ) -> None:
        assert assess(calm(wind_mph=wind_mph), load_lb).level is expected

    def test_load_rule_raises_the_wind_factor_level(self) -> None:
        result = assess(calm(wind_mph=47.0), 42_000)

        assert result.factor_levels[Factor.WIND] is NO_TRAVEL

    def test_load_rule_is_explained(self) -> None:
        result = assess(calm(wind_mph=47.0), 42_000)

        assert result.reasons == (
            "Wind 47 mph → Severe",
            "Wind 47 mph with 42,000 lb load → No Travel",
        )

    def test_light_load_gets_no_load_reason(self) -> None:
        result = assess(calm(wind_mph=47.0), 20_000)

        assert result.reasons == ("Wind 47 mph → Severe",)

    def test_wind_at_55_is_no_travel_for_an_empty_truck(self) -> None:
        result = assess(calm(wind_mph=55.0), 0)

        assert result.level is NO_TRAVEL
        assert result.reasons == ("Wind 55 mph → No Travel",)

    def test_rejects_negative_load(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            assess(calm(), -1)


class TestFactorCombination:
    def test_level_is_the_worst_factor(self) -> None:
        result = assess(calm(wind_mph=30.0, rain_in_hr=0.3, snow_in_hr=0.6), 0)

        assert result.level is HIGH
        assert result.factor_levels == {
            Factor.WIND: MODERATE,
            Factor.RAIN: HIGH,
            Factor.SNOW: MODERATE,
        }

    def test_calm_weather_is_low_with_no_reasons(self) -> None:
        result = assess(calm(), 80_000)

        assert result.level is LOW
        assert result.reasons == ()

    def test_reasons_list_each_factor_at_moderate_or_above(self) -> None:
        result = assess(calm(wind_mph=30.0, rain_in_hr=0.3, snow_in_hr=0.05), 0)

        assert result.reasons == ("Wind 30 mph → Moderate", "Rain 0.3 in/hr → High")

    def test_numbers_are_shown_without_trailing_zeros(self) -> None:
        result = assess(calm(wind_mph=47.5, snow_in_hr=2.25), 0)

        assert result.reasons == ("Wind 47.5 mph → Severe", "Snow 2.25 in/hr → Severe")


class TestUnknownPolicy:
    def test_unknown_rain_does_not_hide_severe_wind(self) -> None:
        result = assess(calm(wind_mph=47.0, rain_in_hr=None), 0)

        assert result.level is SEVERE
        assert result.factor_levels[Factor.RAIN] is UNKNOWN

    def test_unknown_rain_does_not_hide_no_travel_wind(self) -> None:
        assert assess(calm(wind_mph=60.0, rain_in_hr=None), 0).level is NO_TRAVEL

    def test_unknown_rain_with_low_wind_is_unknown(self) -> None:
        assert assess(calm(wind_mph=5.0, rain_in_hr=None), 0).level is UNKNOWN

    def test_unknown_rain_with_high_wind_is_still_unknown(self) -> None:
        assert assess(calm(wind_mph=40.0, rain_in_hr=None), 0).level is UNKNOWN

    def test_unknown_wind_does_not_hide_severe_rain(self) -> None:
        assert assess(calm(wind_mph=None, rain_in_hr=0.7), 0).level is SEVERE

    def test_load_uplift_to_severe_overrides_unknown(self) -> None:
        result = assess(calm(wind_mph=40.0, rain_in_hr=None), 45_000)

        assert result.level is SEVERE

    def test_all_missing_is_unknown(self) -> None:
        assert assess(WeatherSample(), 10_000).level is UNKNOWN

    def test_missing_factors_give_no_reasons(self) -> None:
        assert assess(WeatherSample(), 10_000).reasons == ()


class TestWindBasis:
    SAMPLE = WeatherSample(wind_mph=20.0, gust_mph=50.0, rain_in_hr=0.0, snow_in_hr=0.0)

    def test_sustained_is_the_default(self) -> None:
        assert assess(self.SAMPLE, 0).level is LOW
        assert assess(self.SAMPLE, 0, WindBasis.SUSTAINED).level is LOW

    def test_gust_basis_uses_the_gust_speed(self) -> None:
        result = assess(self.SAMPLE, 0, WindBasis.GUST)

        assert result.level is SEVERE
        assert result.reasons == ("Wind gusts 50 mph → Severe",)

    def test_gust_basis_applies_load_rules_to_the_gust_speed(self) -> None:
        result = assess(self.SAMPLE, 31_000, WindBasis.GUST)

        assert result.level is NO_TRAVEL
        assert result.reasons[-1] == "Wind gusts 50 mph with 31,000 lb load → No Travel"

    def test_missing_gust_is_not_replaced_by_sustained_wind(self) -> None:
        sample = WeatherSample(wind_mph=60.0, gust_mph=None, rain_in_hr=0.0, snow_in_hr=0.0)

        result = assess(sample, 0, WindBasis.GUST)

        assert result.factor_levels[Factor.WIND] is UNKNOWN
        assert result.level is UNKNOWN


optional_amount = st.one_of(st.none(), st.floats(min_value=0, max_value=100, allow_nan=False))
known_amount = st.floats(min_value=0, max_value=100, allow_nan=False)


@given(
    wind=known_amount,
    rain=st.floats(min_value=0, max_value=5, allow_nan=False),
    snow=st.floats(min_value=0, max_value=10, allow_nan=False),
    load_a=st.floats(min_value=0, max_value=100_000, allow_nan=False),
    load_b=st.floats(min_value=0, max_value=100_000, allow_nan=False),
)
def test_a_heavier_load_never_lowers_the_level(
    wind: float, rain: float, snow: float, load_a: float, load_b: float
) -> None:
    light, heavy = sorted((load_a, load_b))
    sample = WeatherSample(wind_mph=wind, rain_in_hr=rain, snow_in_hr=snow)

    assert assess(sample, light).level <= assess(sample, heavy).level


@given(wind=optional_amount, rain=optional_amount, snow=optional_amount, load=known_amount)
def test_overall_level_is_never_below_a_known_factor_and_never_low_when_data_is_missing(
    wind: float | None, rain: float | None, snow: float | None, load: float
) -> None:
    result = assess(WeatherSample(wind_mph=wind, rain_in_hr=rain, snow_in_hr=snow), load)
    known = [level for level in result.factor_levels.values() if level is not UNKNOWN]

    if known and result.level is not UNKNOWN:
        assert result.level >= max(known)
    if len(known) < len(result.factor_levels):
        assert result.level in {UNKNOWN, SEVERE, NO_TRAVEL}
