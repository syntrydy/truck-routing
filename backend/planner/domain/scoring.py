"""Route scoring (SPEC section 4.6): checkpoint levels become per-route risk figures."""

from collections.abc import Sequence

from planner.domain.models import (
    Checkpoint,
    RiskLevel,
    RouteScore,
    Stretch,
    combine_levels,
    is_known,
    max_known,
)
from planner.domain.sampling import stretch_lengths_mi

# A route is low-confidence when more than this share of its miles has no usable weather.
LOW_CONFIDENCE_UNKNOWN_SHARE = 0.20

KNOWN_LEVELS = (
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
)


def build_stretches(checkpoints: Sequence[Checkpoint]) -> list[Stretch]:
    """One stretch per checkpoint except the last, at the worse level of its two ends."""
    lengths = stretch_lengths_mi(checkpoints)
    return [
        Stretch(
            start_index=start.index,
            end_index=end.index,
            length_mi=length,
            level=combine_levels([start.level, end.level]),
        )
        for (start, end), length in zip(
            zip(checkpoints, checkpoints[1:], strict=False), lengths, strict=True
        )
    ]


def score_route(checkpoints: Sequence[Checkpoint], duration_s: float) -> RouteScore:
    """Aggregate the assessed ``checkpoints`` of a route into a ``RouteScore``.

    ``avg_risk`` is the distance-weighted mean of the known stretch levels (0-4) and
    ``None`` when no stretch is known. Unknown miles are reported separately and are
    never counted as LOW, in the average or in ``miles_by_level``.
    """
    if len(checkpoints) < 2:  # noqa: PLR2004 - a route has an origin and a destination
        msg = "a route needs at least two checkpoints"
        raise ValueError(msg)
    distance_mi = checkpoints[-1].distance_mi - checkpoints[0].distance_mi
    if distance_mi <= 0:
        msg = "route has no length"
        raise ValueError(msg)

    stretches = build_stretches(checkpoints)
    miles_by_level = dict.fromkeys(KNOWN_LEVELS, 0.0)
    unknown_miles = 0.0
    for stretch in stretches:
        if is_known(stretch.level):
            miles_by_level[stretch.level] += stretch.length_mi
        else:
            unknown_miles += stretch.length_mi

    known_miles = sum(miles_by_level.values())
    avg_risk = (
        sum(level * miles for level, miles in miles_by_level.items()) / known_miles
        if known_miles > 0
        else None
    )
    return RouteScore(
        distance_mi=distance_mi,
        duration_s=duration_s,
        miles_by_level=miles_by_level,
        unknown_miles=unknown_miles,
        avg_risk=avg_risk,
        worst_level=max_known(stretch.level for stretch in stretches),
        low_confidence=unknown_miles / distance_mi > LOW_CONFIDENCE_UNKNOWN_SHARE,
    )
