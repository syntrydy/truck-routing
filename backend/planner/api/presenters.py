"""Turning a plan result into the JSON of the API, compactly (SPEC section 5).

The payload carries three routes, their checkpoints and 49 frames of a few hundred weather
points, so every number is rounded to what a map or a driver can use and the route lines are
simplified to about 50 meters. ``planner.api.serializers`` describes the same shape for the
OpenAPI schema, and the tests hold the two together.
"""

from datetime import UTC, datetime
from typing import Any

from planner.domain.geometry import simplify
from planner.domain.models import Checkpoint, LatLon, RiskLevel
from planner.domain.ranking import Breakdown, Criterion
from planner.services.models import Heatmap, PlannedRoute, PlanResult

GEOMETRY_TOLERANCE_M = 50.0
COORDINATE_DECIMALS = 5  # route lines: about a meter
PLACE_DECIMALS = 4  # checkpoints and heatmap points: about 10 meters
MILES_DECIMALS = 1
WIND_DECIMALS = 1
PRECIPITATION_DECIMALS = 3
RISK_DECIMALS = 2
KNOWN_LEVELS = tuple(level for level in RiskLevel if level is not RiskLevel.UNKNOWN)
# What each ranking criterion is called to a person, and its unit: miles, the 0 to 4 risk scale,
# or seconds.
CRITERION_LABELS: dict[Criterion, tuple[str, str]] = {
    Criterion.NO_TRAVEL_MI: ("No Travel miles", "mi"),
    Criterion.SEVERE_MI: ("Severe miles", "mi"),
    Criterion.HIGH_MI: ("High-risk miles", "mi"),
    Criterion.AVG_RISK: ("Average risk", "risk"),
    Criterion.DURATION: ("Travel time", "s"),
}


def present_plan(result: PlanResult, request_id: str) -> dict[str, Any]:
    """The response body for ``POST /api/plan``."""
    return {
        "recommended_route_id": result.recommended_route_id,
        "recommendation_reason": result.recommendation_reason,
        "ranking": _ranking(result.ranking),
        "banner": result.banner.value if result.banner else None,
        "routes": [_route(route) for route in result.routes],
        "heatmap": _heatmap(result.heatmap),
        "notes": list(result.notes),
        "meta": {
            "routing_source": result.meta.routing_source,
            "weather_source": result.meta.weather_source,
            "weather_stale": result.meta.weather_stale,
            "generated_at": _time(result.meta.generated_at),
            "request_id": request_id,
        },
    }


def _ranking(ranking: Breakdown) -> dict[str, Any]:
    """The criteria in ranking order, each with every route's value, best first."""
    return {
        "criteria": [
            {
                "id": row.criterion.value,
                "label": CRITERION_LABELS[row.criterion][0],
                "unit": CRITERION_LABELS[row.criterion][1],
                "decisive": row.decisive,
                "values": [
                    {"route_id": route_id, "value": value, "best": best}
                    for route_id, value, best in zip(
                        ranking.route_ids, row.values, row.best, strict=True
                    )
                ],
            }
            for row in ranking.rows
        ]
    }


def _route(route: PlannedRoute) -> dict[str, Any]:
    score = route.score
    return {
        "id": route.id,
        "label": route.label,
        "rank": route.rank,
        "distance_mi": round(route.distance_mi, MILES_DECIMALS),
        "duration_s": round(route.duration_s),
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [round(p.lon, COORDINATE_DECIMALS), round(p.lat, COORDINATE_DECIMALS)]
                for p in simplify(route.points, GEOMETRY_TOLERANCE_M)
            ],
        },
        "summary": {
            "miles_by_level": {
                level.name: round(score.miles_by_level.get(level, 0.0), MILES_DECIMALS)
                for level in KNOWN_LEVELS
            },
            "unknown_miles": round(score.unknown_miles, MILES_DECIMALS),
            "avg_risk": _round(score.avg_risk, RISK_DECIMALS),
            "worst_level": score.worst_level.name,
            "low_confidence": score.low_confidence,
        },
        "checkpoints": [_checkpoint(checkpoint) for checkpoint in route.checkpoints],
    }


def _checkpoint(checkpoint: Checkpoint) -> dict[str, Any]:
    weather = checkpoint.weather
    return {
        "index": checkpoint.index,
        "mile": round(checkpoint.distance_mi, MILES_DECIMALS),
        "lat": round(checkpoint.location.lat, PLACE_DECIMALS),
        "lon": round(checkpoint.location.lon, PLACE_DECIMALS),
        "eta": _time(checkpoint.eta),
        "wind_mph": _round(weather.wind_mph if weather else None, WIND_DECIMALS),
        "gust_mph": _round(weather.gust_mph if weather else None, WIND_DECIMALS),
        "rain_in_hr": _round(weather.rain_in_hr if weather else None, PRECIPITATION_DECIMALS),
        "snow_in_hr": _round(weather.snow_in_hr if weather else None, PRECIPITATION_DECIMALS),
        "level": checkpoint.level.name,
        "reasons": list(checkpoint.reasons),
    }


def _heatmap(heatmap: Heatmap) -> dict[str, Any]:
    return {
        "start": _time(heatmap.start),
        "points": [_place(point) for point in heatmap.points],
        "frames": [
            {
                "risk": list(frame.risk),
                "wind": [_round(value, WIND_DECIMALS) for value in frame.wind_mph],
                "rain": [_round(value, PRECIPITATION_DECIMALS) for value in frame.rain_in_hr],
                "snow": [_round(value, PRECIPITATION_DECIMALS) for value in frame.snow_in_hr],
            }
            for frame in heatmap.frames
        ],
    }


def _place(point: LatLon) -> list[float]:
    """A heatmap point as [lat, lon], the order the SPEC shows."""
    return [round(point.lat, PLACE_DECIMALS), round(point.lon, PLACE_DECIMALS)]


def _round(value: float | None, decimals: int) -> float | None:
    return None if value is None else round(value, decimals)


def _time(moment: datetime) -> str:
    """UTC with a Z, to the second (the format has no fraction, so none is written)."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
