import math
from collections.abc import Callable

import pytest
from hypothesis import given
from hypothesis import strategies as st

from planner.domain.models import RiskLevel
from planner.domain.risk import (
    RAIN_BANDS,
    SNOW_BANDS,
    WIND_BANDS,
    BandTable,
    classify_rain,
    classify_snow,
    classify_wind,
)

LOW = RiskLevel.LOW
MODERATE = RiskLevel.MODERATE
HIGH = RiskLevel.HIGH
SEVERE = RiskLevel.SEVERE
NO_TRAVEL = RiskLevel.NO_TRAVEL

Classifier = Callable[[float | None], RiskLevel]


@pytest.mark.parametrize(
    ("wind_mph", "expected"),
    [
        (0.0, LOW),
        (24.99, LOW),
        (25.0, MODERATE),
        (34.99, MODERATE),
        (35.0, HIGH),
        (44.99, HIGH),
        (45.0, SEVERE),
        (54.99, SEVERE),
        (55.0, NO_TRAVEL),
        (55.01, NO_TRAVEL),
        (120.0, NO_TRAVEL),
    ],
)
def test_wind_bands(wind_mph: float, expected: RiskLevel) -> None:
    assert classify_wind(wind_mph) is expected


@pytest.mark.parametrize(
    ("rain_in_hr", "expected"),
    [
        (0.0, LOW),
        (0.0999, LOW),
        (0.10, MODERATE),
        (0.2499, MODERATE),
        (0.25, HIGH),
        (0.4999, HIGH),
        (0.50, SEVERE),
        (0.9999, SEVERE),
        (1.00, SEVERE),
        (1.0001, NO_TRAVEL),
        (5.0, NO_TRAVEL),
    ],
)
def test_rain_bands(rain_in_hr: float, expected: RiskLevel) -> None:
    assert classify_rain(rain_in_hr) is expected


@pytest.mark.parametrize(
    ("snow_in_hr", "expected"),
    [
        (0.0, LOW),
        (0.4999, LOW),
        (0.5, MODERATE),
        (0.9999, MODERATE),
        (1.0, HIGH),
        (1.9999, HIGH),
        (2.0, SEVERE),
        (2.99, SEVERE),
        (3.0, SEVERE),
        (3.0001, NO_TRAVEL),
        (10.0, NO_TRAVEL),
    ],
)
def test_snow_bands(snow_in_hr: float, expected: RiskLevel) -> None:
    assert classify_snow(snow_in_hr) is expected


@pytest.mark.parametrize("classifier", [classify_wind, classify_rain, classify_snow])
class TestMissingValues:
    def test_none_is_unknown(self, classifier: Classifier) -> None:
        assert classifier(None) is RiskLevel.UNKNOWN

    def test_nan_is_unknown_rather_than_low(self, classifier: Classifier) -> None:
        assert classifier(math.nan) is RiskLevel.UNKNOWN

    def test_negative_values_are_low(self, classifier: Classifier) -> None:
        assert classifier(-1.0) is RiskLevel.LOW

    def test_infinity_is_no_travel(self, classifier: Classifier) -> None:
        assert classifier(math.inf) is RiskLevel.NO_TRAVEL


@pytest.mark.parametrize(
    "classifier",
    [classify_wind, classify_rain, classify_snow],
    ids=["wind", "rain", "snow"],
)
@given(
    a=st.floats(min_value=0, max_value=200, allow_nan=False),
    b=st.floats(min_value=0, max_value=200, allow_nan=False),
)
def test_classification_is_monotonic_non_decreasing(
    classifier: Classifier, a: float, b: float
) -> None:
    low, high = sorted((a, b))

    assert classifier(low) <= classifier(high)


@pytest.mark.parametrize(
    "bands",
    [WIND_BANDS, RAIN_BANDS, SNOW_BANDS],
    ids=["wind", "rain", "snow"],
)
def test_band_tables_list_the_most_severe_band_first(bands: BandTable) -> None:
    thresholds = [edge.threshold for edge in bands]
    levels = [edge.level for edge in bands]

    assert thresholds == sorted(thresholds, reverse=True)
    assert levels == [NO_TRAVEL, SEVERE, HIGH, MODERATE]
