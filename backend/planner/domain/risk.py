"""Risk classification of a weather sample (SPEC section 4.5).

Band classification: each factor is described by a table of band edges, checked from the most to the
least severe. A value reaches a band when it is at or above the edge, or strictly
above it for edges marked exclusive. Values below every edge are ``LOW``; a missing
value is ``UNKNOWN``, never ``LOW``.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import NamedTuple

from planner.domain.models import RiskLevel, WeatherSample, combine_levels, is_known, max_known


class Edge(NamedTuple):
    """Lower edge of a band: values reach ``level`` at/above (or strictly above) ``threshold``."""

    threshold: float
    level: RiskLevel
    inclusive: bool = True


type BandTable = tuple[Edge, ...]

# Sustained wind in mph. NO_TRAVEL starts at 55 inclusive.
WIND_BANDS: BandTable = (
    Edge(55.0, RiskLevel.NO_TRAVEL),
    Edge(45.0, RiskLevel.SEVERE),
    Edge(35.0, RiskLevel.HIGH),
    Edge(25.0, RiskLevel.MODERATE),
)

# Rain in inches per hour. SEVERE includes exactly 1.00; NO_TRAVEL is strictly above.
RAIN_BANDS: BandTable = (
    Edge(1.00, RiskLevel.NO_TRAVEL, inclusive=False),
    Edge(0.50, RiskLevel.SEVERE),
    Edge(0.25, RiskLevel.HIGH),
    Edge(0.10, RiskLevel.MODERATE),
)

# Snow in inches per hour. SEVERE includes exactly 3.0; NO_TRAVEL is strictly above.
SNOW_BANDS: BandTable = (
    Edge(3.0, RiskLevel.NO_TRAVEL, inclusive=False),
    Edge(2.0, RiskLevel.SEVERE),
    Edge(1.0, RiskLevel.HIGH),
    Edge(0.5, RiskLevel.MODERATE),
)


def classify(value: float | None, bands: BandTable) -> RiskLevel:
    """Return the level of ``value`` in ``bands``; ``None`` and NaN are ``UNKNOWN``."""
    if value is None or math.isnan(value):
        return RiskLevel.UNKNOWN
    for edge in bands:
        if value > edge.threshold or (edge.inclusive and value == edge.threshold):
            return edge.level
    return RiskLevel.LOW


def classify_wind(wind_mph: float | None) -> RiskLevel:
    """Classify wind speed in mph."""
    return classify(wind_mph, WIND_BANDS)


def classify_rain(rain_in_hr: float | None) -> RiskLevel:
    """Classify rain rate in inches per hour."""
    return classify(rain_in_hr, RAIN_BANDS)


def classify_snow(snow_in_hr: float | None) -> RiskLevel:
    """Classify snowfall rate in inches per hour."""
    return classify(snow_in_hr, SNOW_BANDS)


class Factor(StrEnum):
    """The weather factors that make up a checkpoint assessment."""

    WIND = "wind"
    RAIN = "rain"
    SNOW = "snow"


class WindBasis(StrEnum):
    """Which wind value drives the wind factor and the load rules."""

    SUSTAINED = "sustained"
    GUST = "gust"


class LoadRule(NamedTuple):
    """Raises the wind level to ``level`` for loads strictly above ``load_above_lb``.

    Applies to wind speeds in ``[wind_from_mph, wind_below_mph)``.
    """

    wind_from_mph: float
    wind_below_mph: float
    load_above_lb: float
    level: RiskLevel


# Applied in order after the band tables. Wind >= 55 mph is NO_TRAVEL for any load and
# is already the top wind band, so it needs no rule here.
LOAD_RULES: tuple[LoadRule, ...] = (
    LoadRule(45.0, 55.0, 30_000.0, RiskLevel.NO_TRAVEL),
    LoadRule(35.0, 45.0, 40_000.0, RiskLevel.SEVERE),
)

LEVEL_LABELS: Mapping[RiskLevel, str] = {
    RiskLevel.UNKNOWN: "Unknown",
    RiskLevel.LOW: "Low",
    RiskLevel.MODERATE: "Moderate",
    RiskLevel.HIGH: "High",
    RiskLevel.SEVERE: "Severe",
    RiskLevel.NO_TRAVEL: "No Travel",
}


@dataclass(frozen=True, slots=True)
class Assessment:
    """Risk of one checkpoint: overall level, level per factor and the reasons why.

    ``factor_levels[Factor.WIND]`` already includes any load-rule uplift.
    """

    level: RiskLevel
    factor_levels: Mapping[Factor, RiskLevel]
    reasons: tuple[str, ...]


def assess(
    sample: WeatherSample,
    load_lb: float,
    wind_basis: WindBasis = WindBasis.SUSTAINED,
) -> Assessment:
    """Assess the risk of ``sample`` for a truck carrying ``load_lb`` pounds.

    A missing value makes its factor UNKNOWN. The overall level is UNKNOWN when any
    factor is UNKNOWN and no known factor is already SEVERE or worse, so an outage can
    never hide known danger and never reads as LOW.
    """
    if load_lb < 0:
        msg = f"load must not be negative, got {load_lb}"
        raise ValueError(msg)

    wind_mph = sample.gust_mph if wind_basis is WindBasis.GUST else sample.wind_mph
    wind_subject = "Wind gusts" if wind_basis is WindBasis.GUST else "Wind"
    wind_band = classify_wind(wind_mph)
    rain_level = classify_rain(sample.rain_in_hr)
    snow_level = classify_snow(sample.snow_in_hr)

    reasons: list[str] = []
    wind_level = wind_band
    if wind_mph is not None:
        wind_text = f"{wind_subject} {_format_number(wind_mph)} mph"
        _add_factor_reason(reasons, wind_text, wind_band)
        for rule in _triggered_load_rules(wind_mph, load_lb):
            wind_level = max_known([wind_level, rule.level])
            reasons.append(f"{wind_text} with {load_lb:,.0f} lb load → {LEVEL_LABELS[rule.level]}")
    if sample.rain_in_hr is not None:
        _add_factor_reason(reasons, f"Rain {_format_number(sample.rain_in_hr)} in/hr", rain_level)
    if sample.snow_in_hr is not None:
        _add_factor_reason(reasons, f"Snow {_format_number(sample.snow_in_hr)} in/hr", snow_level)

    factor_levels = {
        Factor.WIND: wind_level,
        Factor.RAIN: rain_level,
        Factor.SNOW: snow_level,
    }
    return Assessment(
        level=combine_levels(factor_levels.values()),
        factor_levels=factor_levels,
        reasons=tuple(reasons),
    )


def _triggered_load_rules(wind_mph: float, load_lb: float) -> list[LoadRule]:
    return [
        rule
        for rule in LOAD_RULES
        if rule.wind_from_mph <= wind_mph < rule.wind_below_mph and load_lb > rule.load_above_lb
    ]


def _add_factor_reason(reasons: list[str], text: str, level: RiskLevel) -> None:
    if is_known(level) and level >= RiskLevel.MODERATE:
        reasons.append(f"{text} → {LEVEL_LABELS[level]}")


def _format_number(value: float) -> str:
    """Format with up to two decimals, without trailing zeros (47.0 -> '47')."""
    return f"{value:.2f}".rstrip("0").rstrip(".")
