"""What goes into the plan service and what comes out of it."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from planner.domain.corridor import CorridorFrame
from planner.domain.models import Checkpoint, LatLon, RouteScore

ALLOWED_INTERVALS_MI = (10, 25, 50)


class TooClose(Exception):  # noqa: N818 - named for the API error code it maps to
    """Origin and destination are less than a mile apart (HTTP 400 TOO_CLOSE)."""


class PlanBanner(StrEnum):
    """Warnings shown above the recommendation. At most one is set."""

    NO_SAFE_ROUTE = "NO_SAFE_ROUTE"
    WEATHER_UNAVAILABLE = "WEATHER_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class PlanRequest:
    """A validated request. The API layer checks user input; these are the invariants."""

    origin: LatLon
    destination: LatLon
    departure: datetime
    load_lb: float
    interval_mi: int

    def __post_init__(self) -> None:
        if self.departure.tzinfo is None:
            msg = "departure must be timezone-aware"
            raise ValueError(msg)
        if self.load_lb < 0:
            msg = "load must not be negative"
            raise ValueError(msg)
        if self.interval_mi not in ALLOWED_INTERVALS_MI:
            msg = f"interval must be one of {ALLOWED_INTERVALS_MI}"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class PlannedRoute:
    """One route with its checkpoints assessed and its risk scored."""

    id: str
    label: str
    rank: int
    points: tuple[LatLon, ...]
    distance_mi: float
    duration_s: float
    score: RouteScore
    checkpoints: tuple[Checkpoint, ...]


@dataclass(frozen=True, slots=True)
class Heatmap:
    """The weather corridor: grid points and an hourly frame of readings for each."""

    start: datetime
    points: tuple[LatLon, ...]
    frames: tuple[CorridorFrame, ...]


@dataclass(frozen=True, slots=True)
class PlanMeta:
    """Where the data came from."""

    routing_source: str
    weather_source: str
    weather_stale: bool
    generated_at: datetime


@dataclass(frozen=True, slots=True)
class PlanResult:
    """A complete plan: routes best first, the recommendation and why, and the heatmap."""

    recommended_route_id: str | None
    recommendation_reason: str | None
    banner: PlanBanner | None
    routes: tuple[PlannedRoute, ...]
    heatmap: Heatmap
    notes: tuple[str, ...]
    meta: PlanMeta
