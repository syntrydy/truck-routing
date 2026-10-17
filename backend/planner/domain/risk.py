"""Weather band classification (SPEC section 4.5).

Each factor is described by a table of band edges, checked from the most to the
least severe. A value reaches a band when it is at or above the edge, or strictly
above it for edges marked exclusive. Values below every edge are ``LOW``; a missing
value is ``UNKNOWN``, never ``LOW``.
"""

import math
from typing import NamedTuple

from planner.domain.models import RiskLevel


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
