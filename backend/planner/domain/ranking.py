"""Route ranking and the recommendation reason (SPEC section 4.7).

Routes are ordered by exposure to the worst conditions first: No Travel miles, then
Severe, then High, then average risk, then duration. Miles are rounded to a tenth and
average risk to a hundredth so float noise cannot decide an order.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import NamedTuple

from planner.domain.models import RiskLevel, RouteScore

MILES_DECIMALS = 1
AVG_RISK_DECIMALS = 2
SECONDS_PER_MINUTE = 60
MINUTES_PER_HOUR = 60


class Banner(StrEnum):
    """Warnings the UI shows above the recommendation."""

    NO_SAFE_ROUTE = "NO_SAFE_ROUTE"


class Criterion(StrEnum):
    """What routes are compared on, in the order the ranking applies them."""

    NO_TRAVEL_MI = "NO_TRAVEL_MI"
    SEVERE_MI = "SEVERE_MI"
    HIGH_MI = "HIGH_MI"
    AVG_RISK = "AVG_RISK"
    DURATION = "DURATION"


@dataclass(frozen=True, slots=True)
class ScoredRoute:
    """A route identified by ``route_id`` together with its score."""

    route_id: str
    score: RouteScore


@dataclass(frozen=True, slots=True)
class CriterionRow:
    """One criterion across the ranked routes.

    ``values`` and ``best`` are in the order of ``Breakdown.route_ids``. A value is what the
    ranking compared: miles to a tenth, average risk to a hundredth (``None`` when unknown),
    duration in seconds. ``decisive`` marks the first criterion on which the two best routes
    differ, the one that decided between them.
    """

    criterion: Criterion
    values: tuple[float | None, ...]
    best: tuple[bool, ...]
    decisive: bool


@dataclass(frozen=True, slots=True)
class Breakdown:
    """The ranking laid out: the routes best first, and a row for each criterion."""

    route_ids: tuple[str, ...]
    rows: tuple[CriterionRow, ...]


@dataclass(frozen=True, slots=True)
class Recommendation:
    """Routes best first, plus the pick and why.

    ``recommended_route_id`` and ``reason`` are ``None`` when every route has No Travel
    miles; ``banner`` is then ``NO_SAFE_ROUTE``. The routes are still ranked.
    """

    ordered: tuple[ScoredRoute, ...]
    recommended_route_id: str | None
    reason: str | None
    banner: Banner | None
    breakdown: Breakdown


class RankKey(NamedTuple):
    """Sort key of a route; lower is better."""

    no_travel_mi: float
    severe_mi: float
    high_mi: float
    avg_risk: float
    duration_s: float


# The key fields in the order of the criteria they stand for.
_CRITERIA = tuple(zip(Criterion, RankKey._fields, strict=True))


def rank_key(score: RouteScore) -> RankKey:
    """Build the rounded sort key. An unknown average risk sorts after any known one."""
    avg_risk = math.inf if score.avg_risk is None else round(score.avg_risk, AVG_RISK_DECIMALS)
    return RankKey(
        no_travel_mi=round(score.miles_by_level.get(RiskLevel.NO_TRAVEL, 0.0), MILES_DECIMALS),
        severe_mi=round(score.miles_by_level.get(RiskLevel.SEVERE, 0.0), MILES_DECIMALS),
        high_mi=round(score.miles_by_level.get(RiskLevel.HIGH, 0.0), MILES_DECIMALS),
        avg_risk=avg_risk,
        duration_s=score.duration_s,
    )


def rank_routes(routes: Sequence[ScoredRoute]) -> Recommendation:
    """Order ``routes`` best first and recommend one, unless all have No Travel miles.

    Exact ties keep the order they were given in.
    """
    if not routes:
        msg = "no routes to rank"
        raise ValueError(msg)

    keyed = sorted(((rank_key(route.score), route) for route in routes), key=lambda pair: pair[0])
    ordered = tuple(route for _, route in keyed)
    best_key = keyed[0][0]
    breakdown = _breakdown([(key, route.route_id) for key, route in keyed])

    if best_key.no_travel_mi > 0:
        return Recommendation(
            ordered=ordered,
            recommended_route_id=None,
            reason=None,
            banner=Banner.NO_SAFE_ROUTE,
            breakdown=breakdown,
        )
    reason = (
        "Only one route is available"
        if len(keyed) == 1
        else _separating_reason(best_key, keyed[1][0])
    )
    return Recommendation(
        ordered=ordered,
        recommended_route_id=ordered[0].route_id,
        reason=reason,
        banner=None,
        breakdown=breakdown,
    )


def _breakdown(keyed: Sequence[tuple[RankKey, str]]) -> Breakdown:
    """The criteria across the routes, best first, with the deciding one marked."""
    keys = [key for key, _ in keyed]
    decisive = _first_difference(keys[0], keys[1]) if len(keys) > 1 else None
    rows = []
    for criterion, field in _CRITERIA:
        raw = [getattr(key, field) for key in keys]
        least = min(raw)
        rows.append(
            CriterionRow(
                criterion=criterion,
                values=tuple(None if math.isinf(value) else value for value in raw),
                best=tuple(value == least for value in raw),
                decisive=criterion is decisive,
            )
        )
    return Breakdown(route_ids=tuple(route_id for _, route_id in keyed), rows=tuple(rows))


def _first_difference(best: RankKey, runner_up: RankKey) -> Criterion | None:
    """The first criterion, in ranking order, on which the two routes differ."""
    for criterion, field in _CRITERIA:
        if getattr(best, field) != getattr(runner_up, field):
            return criterion
    return None


def _separating_reason(best: RankKey, runner_up: RankKey) -> str:
    """Phrase the first criterion on which ``best`` beats ``runner_up``."""
    criterion = _first_difference(best, runner_up)
    if criterion is Criterion.NO_TRAVEL_MI:
        return (
            f"Fewest No Travel miles ({_miles(best.no_travel_mi)} vs "
            f"{_miles(runner_up.no_travel_mi)} on the next best route)"
        )
    if criterion is Criterion.SEVERE_MI:
        return (
            f"Fewest Severe miles ({_miles(best.severe_mi)} vs "
            f"{_miles(runner_up.severe_mi)} on the next best route)"
        )
    if criterion is Criterion.HIGH_MI:
        return (
            f"Fewest High-risk miles ({_miles(best.high_mi)} vs "
            f"{_miles(runner_up.high_mi)} on the next best route)"
        )
    if criterion is Criterion.AVG_RISK:
        return (
            f"Lowest average risk ({_risk(best.avg_risk)} vs "
            f"{_risk(runner_up.avg_risk)} on the next best route)"
        )
    if criterion is Criterion.DURATION:
        return (
            "Same risk profile and the fastest "
            f"({_duration(best.duration_s, runner_up.duration_s)})"
        )
    return "Identical risk and duration to the next route"


def _miles(value: float) -> str:
    return f"{value:.{MILES_DECIMALS}f} mi"


def _risk(value: float) -> str:
    return "unknown" if math.isinf(value) else f"{value:.{AVG_RISK_DECIMALS}f}"


def _duration(best_s: float, other_s: float) -> str:
    """'2 h 10 min vs 2 h 25 min'; seconds are added when the minutes would look equal."""
    best, other = _hours_minutes(best_s), _hours_minutes(other_s)
    if best == other:
        best, other = _hours_minutes(best_s, seconds=True), _hours_minutes(other_s, seconds=True)
    return f"{best} vs {other}"


def _hours_minutes(total_s: float, *, seconds: bool = False) -> str:
    if seconds:
        minutes, secs = divmod(round(total_s), SECONDS_PER_MINUTE)
        hours, minutes = divmod(minutes, MINUTES_PER_HOUR)
        return f"{hours} h {minutes} min {secs} s" if hours else f"{minutes} min {secs} s"
    minutes_total = round(total_s / SECONDS_PER_MINUTE)
    hours, minutes = divmod(minutes_total, MINUTES_PER_HOUR)
    return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"
