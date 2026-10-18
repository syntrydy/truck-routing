"""The plan service: providers and the pure domain wired into one pipeline (SPEC section 4)."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from time import monotonic as default_monotonic
from typing import NamedTuple

from planner.domain.corridor import FRAME_COUNT, build_frames, build_grid
from planner.domain.geometry import METERS_PER_MILE, cumulative_distances_m, haversine_m
from planner.domain.models import Checkpoint, LatLon, WeatherSample
from planner.domain.ranking import Banner, ScoredRoute, rank_routes
from planner.domain.risk import WindBasis, assess
from planner.domain.routes_select import (
    MAX_ROUTES,
    RouteCandidate,
    select_routes,
    via_points,
)
from planner.domain.sampling import sample_checkpoints, truck_durations_s
from planner.domain.scoring import score_route
from planner.domain.weather_select import select_weather
from planner.infra.errors import UpstreamContractError, UpstreamTimeout, UpstreamUnavailable
from planner.infra.resilience import deadline_scope
from planner.providers.protocols import (
    NoRoute,
    ProviderRoute,
    RoutingProvider,
    RoutingResult,
    WeatherProvider,
    WeatherResult,
    rounded_point,
)
from planner.services.models import (
    Heatmap,
    PlanBanner,
    PlanMeta,
    PlannedRoute,
    PlanRequest,
    PlanResult,
    TooClose,
)

PLAN_BUDGET_S = 20.0
MIN_TRIP_MI = 1.0
SNAP_WARNING_M = 5_000.0
HEAVY_LOAD_LB = 80_000
HEATMAP_HOURS = FRAME_COUNT - 1
MAX_WEATHER_DAYS = 16
# A detour that cannot be fetched only costs an extra route, not the plan.
DETOUR_FAILURES = (UpstreamUnavailable, UpstreamTimeout, UpstreamContractError, NoRoute)

Now = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class _Draft:
    """A selected route with checkpoints but no weather yet."""

    id: str
    label: str
    points: tuple[LatLon, ...]
    distance_mi: float
    duration_s: float
    checkpoints: tuple[Checkpoint, ...]


class PlanService:
    """Plans a trip: routes, checkpoints with weather risk, a ranking and a heatmap."""

    def __init__(  # noqa: PLR0913 - the collaborators and tunables of the facade
        self,
        routing: RoutingProvider,
        weather: WeatherProvider,
        *,
        max_speed_mph: float,
        wind_basis: WindBasis,
        budget_s: float = PLAN_BUDGET_S,
        now: Now = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = default_monotonic,
    ) -> None:
        self._routing = routing
        self._weather = weather
        self._max_speed_mph = max_speed_mph
        self._wind_basis = wind_basis
        self._budget_s = budget_s
        self._now = now
        self._monotonic = monotonic

    def plan(self, request: PlanRequest) -> PlanResult:
        """Plan ``request``. Raises ``TooClose``, ``NoRoute`` or a typed upstream error."""
        if haversine_m(request.origin, request.destination) < MIN_TRIP_MI * METERS_PER_MILE:
            msg = "origin and destination are less than a mile apart"
            raise TooClose(msg)

        with deadline_scope(self._budget_s, self._monotonic):
            routing, candidates, notes = self._candidate_routes(request)
            selection = select_routes([candidate for candidate, _ in candidates])
            by_id = {candidate.route_id: route for candidate, route in candidates}
            drafts = [
                self._draft(f"r{index + 1}", chr(ord("A") + index), by_id[chosen.route_id], request)
                for index, chosen in enumerate(selection.routes)
            ]
            grid = build_grid([draft.points for draft in drafts])
            weather = self._weather_for(drafts, grid.points, request)
            planned = [self._assess(draft, weather, request) for draft in drafts]
            recommendation = rank_routes([ScoredRoute(route.id, route.score) for route in planned])
            frames = build_frames(
                [weather.series.get(rounded_point(point)) for point in grid.points],
                request.departure,
                request.load_lb,
                self._wind_basis,
            )

        ranked = _in_order(planned, [route.route_id for route in recommendation.ordered])
        gaps = _weather_gaps(drafts, grid.points, weather)
        banner = _banner(recommendation.banner, gaps)
        return PlanResult(
            recommended_route_id=recommendation.recommended_route_id,
            recommendation_reason=recommendation.reason,
            ranking=recommendation.breakdown,
            banner=banner,
            routes=tuple(replace(route, rank=rank) for rank, route in enumerate(ranked, 1)),
            heatmap=Heatmap(
                start=request.departure.astimezone(UTC).replace(minute=0, second=0, microsecond=0),
                points=grid.points,
                frames=tuple(frames),
            ),
            notes=(
                f"ETAs assume continuous driving at ≤ {self._max_speed_mph:g} mph",
                *selection.notes,
                *notes,
                *_weather_notes(weather, gaps),
                *_load_notes(request),
            ),
            meta=PlanMeta(
                routing_source=routing.source,
                weather_source=weather.source,
                weather_stale=weather.stale,
                generated_at=self._now(),
            ),
        )

    def _candidate_routes(
        self, request: PlanRequest
    ) -> tuple[RoutingResult, list[tuple[RouteCandidate, ProviderRoute]], list[str]]:
        """The provider's routes, plus detours through via points when there are too few."""
        primary = self._routing.routes(request.origin, request.destination)
        candidates = [
            (_candidate(f"c{index}", route, is_detour=False), route)
            for index, route in enumerate(primary.routes)
        ]
        notes: list[str] = []
        if primary.snap_distance_m > SNAP_WARNING_M:
            notes.append(_snap_note(primary.snap_distance_m))
        if len(candidates) < MAX_ROUTES:
            fastest = min(primary.routes, key=lambda route: route.duration_s)
            failed = False
            for via in via_points(request.origin, request.destination, fastest.points):
                try:
                    detour = self._routing.route_via(request.origin, via, request.destination)
                except DETOUR_FAILURES:
                    failed = True
                    continue
                candidates.extend(
                    (_candidate(f"c{len(candidates)}", route, is_detour=True), route)
                    for route in detour.routes
                )
            if failed:
                notes.append("Some alternative routes could not be loaded")
        return primary, candidates, notes

    def _draft(
        self, route_id: str, label: str, route: ProviderRoute, request: PlanRequest
    ) -> _Draft:
        # The provider's segment times leave out turn and signal delays that its route total
        # includes (about 3% for OSRM), so they are scaled up to that total before the
        # speed limit is applied.
        scaled = _scale_up_to(route.segment_durations_s, route.duration_s)
        durations = truck_durations_s(route.points, scaled, self._max_speed_mph)
        checkpoints = sample_checkpoints(
            route.points, durations, request.departure, request.interval_mi
        )
        return _Draft(
            id=route_id,
            label=f"Route {label}",
            points=route.points,
            distance_mi=cumulative_distances_m(route.points)[-1] / METERS_PER_MILE,
            duration_s=sum(durations),
            checkpoints=tuple(checkpoints),
        )

    def _weather_for(
        self, drafts: Sequence[_Draft], grid: Sequence[LatLon], request: PlanRequest
    ) -> WeatherResult:
        places = [cp.location for draft in drafts for cp in draft.checkpoints]
        departure_hour = request.departure.astimezone(UTC).replace(
            minute=0, second=0, microsecond=0
        )
        latest_eta = max(cp.eta for draft in drafts for cp in draft.checkpoints)
        last = max(latest_eta, departure_hour + timedelta(hours=HEATMAP_HOURS))
        first_day = departure_hour.date()
        last_day = min(
            last.astimezone(UTC).date(), first_day + timedelta(days=MAX_WEATHER_DAYS - 1)
        )
        return self._weather.hourly([*places, *grid], first_day, last_day)

    def _assess(self, draft: _Draft, weather: WeatherResult, request: PlanRequest) -> PlannedRoute:
        checkpoints = []
        for checkpoint in draft.checkpoints:
            series = weather.series.get(rounded_point(checkpoint.location))
            sample = select_weather(series, checkpoint.eta) if series else WeatherSample()
            assessment = assess(sample, request.load_lb, self._wind_basis)
            checkpoints.append(
                replace(
                    checkpoint,
                    weather=sample,
                    level=assessment.level,
                    reasons=assessment.reasons,
                )
            )
        return PlannedRoute(
            id=draft.id,
            label=draft.label,
            rank=0,
            points=draft.points,
            distance_mi=draft.distance_mi,
            duration_s=draft.duration_s,
            score=score_route(checkpoints, draft.duration_s),
            checkpoints=tuple(checkpoints),
        )


def _candidate(route_id: str, route: ProviderRoute, *, is_detour: bool) -> RouteCandidate:
    return RouteCandidate(
        route_id=route_id,
        points=route.points,
        distance_m=route.distance_m,
        duration_s=route.duration_s,
        is_detour=is_detour,
    )


def _scale_up_to(durations: Sequence[float], total: float) -> list[float]:
    """The segment times, scaled up (never down) so that they add up to ``total``."""
    current = sum(durations)
    factor = max(1.0, total / current) if current > 0 else 1.0
    return [duration * factor for duration in durations]


def _in_order(routes: Sequence[PlannedRoute], ids: Sequence[str]) -> list[PlannedRoute]:
    by_id = {route.id: route for route in routes}
    return [by_id[route_id] for route_id in ids]


class _WeatherGaps(NamedTuple):
    """Places without weather: where a route has a checkpoint, and heatmap cells off the routes."""

    checkpoints: int
    cells: int


def _weather_gaps(
    drafts: Sequence[_Draft], grid: Sequence[LatLon], weather: WeatherResult
) -> _WeatherGaps:
    """Count each place once, as a checkpoint place if any route has a checkpoint there."""
    on_routes = {rounded_point(cp.location) for draft in drafts for cp in draft.checkpoints}
    off_routes = {rounded_point(point) for point in grid} - on_routes

    def lacking(places: set[LatLon]) -> int:
        return sum(1 for place in places if weather.series.get(place) is None)

    return _WeatherGaps(checkpoints=lacking(on_routes), cells=lacking(off_routes))


def _banner(ranking: Banner | None, gaps: _WeatherGaps) -> PlanBanner | None:
    """No safe route outranks missing weather: known danger is the more important warning.

    Only a gap at a checkpoint warns: a gap among the map's cells changes no route's levels.
    """
    if ranking is Banner.NO_SAFE_ROUTE:
        return PlanBanner.NO_SAFE_ROUTE
    if gaps.checkpoints > 0:
        return PlanBanner.WEATHER_UNAVAILABLE
    return None


def _snap_note(snap_distance_m: float) -> str:
    return (
        f"The origin or destination is {snap_distance_m / 1000:.1f} km from the nearest road; "
        "the route starts or ends at the road"
    )


def _weather_notes(weather: WeatherResult, gaps: _WeatherGaps) -> list[str]:
    notes = []
    if weather.stale:
        notes.append("Weather data may be out of date because the forecast service is unavailable")
    if gaps.checkpoints:
        places = "location" if gaps.checkpoints == 1 else "locations"
        notes.append(
            f"Weather is unavailable for {gaps.checkpoints} {places}; "
            "their risk is shown as unknown"
        )
    if gaps.cells:
        subject = (
            "cell of the weather map has" if gaps.cells == 1 else "cells of the weather map have"
        )
        notes.append(f"{gaps.cells} {subject} no forecast; they are shown in grey")
    return notes


def _load_notes(request: PlanRequest) -> list[str]:
    if request.load_lb > HEAVY_LOAD_LB:
        return [f"A load above {HEAVY_LOAD_LB:,} lb exceeds the usual legal limit"]
    return []
