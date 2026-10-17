"""Immutable value objects shared by the pure domain modules.

Units: distances in miles unless a name says otherwise, speeds in mph, precipitation
in inches per hour, durations in seconds, all datetimes timezone-aware (UTC).
"""

from collections.abc import Iterable
from enum import IntEnum


class RiskLevel(IntEnum):
    """Ordered risk level of a weather factor, checkpoint, stretch or route.

    ``UNKNOWN`` is a sentinel for "no usable weather data", not a level: it has no
    place in the ordering. Its value (-1) matches the heatmap wire format, but
    comparing it with ``<``/``>`` is meaningless. Use ``is_known`` and ``max_known``.
    """

    UNKNOWN = -1
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4


def is_known(level: RiskLevel) -> bool:
    """Return whether ``level`` is a real level rather than the UNKNOWN sentinel."""
    return level is not RiskLevel.UNKNOWN


def max_known(levels: Iterable[RiskLevel]) -> RiskLevel:
    """Return the highest known level, ignoring UNKNOWN.

    Returns ``RiskLevel.UNKNOWN`` when there is no known level (empty input or all
    UNKNOWN), so unknown data can never be mistaken for ``LOW``.
    """
    known = [level for level in levels if is_known(level)]
    return max(known, default=RiskLevel.UNKNOWN)
