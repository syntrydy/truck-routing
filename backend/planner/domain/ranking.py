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


@dataclass(frozen=True, slots=True)
class ScoredRoute:
    """A route identified by ``route_id`` together with its score."""

    route_id: str
    score: RouteScore


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


class RankKey(NamedTuple):
    """Sort key of a route; lower is better."""

    no_travel_mi: float
    severe_mi: float
    high_mi: float
    avg_risk: float
    duration_s: float


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

    if best_key.no_travel_mi > 0:
        return Recommendation(
            ordered=ordered,
            recommended_route_id=None,
            reason=None,
            banner=Banner.NO_SAFE_ROUTE,
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
    )


def _separating_reason(best: RankKey, runner_up: RankKey) -> str:
    """Phrase the first criterion on which ``best`` beats ``runner_up``."""
    if best.no_travel_mi != runner_up.no_travel_mi:
        return (
            f"Fewest No Travel miles ({_miles(best.no_travel_mi)} vs "
            f"{_miles(runner_up.no_travel_mi)} on the next best route)"
        )
    if best.severe_mi != runner_up.severe_mi:
        return (
            f"Fewest Severe miles ({_miles(best.severe_mi)} vs "
            f"{_miles(runner_up.severe_mi)} on the next best route)"
        )
    if best.high_mi != runner_up.high_mi:
        return (
            f"Fewest High-risk miles ({_miles(best.high_mi)} vs "
            f"{_miles(runner_up.high_mi)} on the next best route)"
        )
    if best.avg_risk != runner_up.avg_risk:
        return (
            f"Lowest average risk ({_risk(best.avg_risk)} vs "
            f"{_risk(runner_up.avg_risk)} on the next best route)"
        )
    if best.duration_s != runner_up.duration_s:
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
