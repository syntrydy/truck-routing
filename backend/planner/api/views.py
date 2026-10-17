"""API views."""

from datetime import UTC, datetime

from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from planner.api.middleware import get_request_id
from planner.api.presenters import present_plan
from planner.api.ratelimit import geocode_rate, plan_rate
from planner.api.serializers import (
    ErrorEnvelopeSerializer,
    GeocodeResponseSerializer,
    HealthSerializer,
    PlanRequestSerializer,
    PlanResponseSerializer,
    ReadySerializer,
    parse_plan_request,
)
from planner.infra.resilience import BreakerState
from planner.providers.protocols import MAX_QUERY_LENGTH, MIN_QUERY_LENGTH, normalize_query
from planner.services.container import get_container


def utc_now() -> datetime:
    """The current time; a function so that tests can fix it."""
    return datetime.now(UTC)


class HealthView(APIView):
    """Liveness probe. Makes no upstream calls."""

    @extend_schema(responses=HealthSerializer, operation_id="health")
    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})


class ReadyView(APIView):
    """Readiness probe: the state of each provider's circuit breaker and of the cache.

    It makes no upstream call. The answer is 200 even when degraded, because the API still
    serves requests: routes fall back, weather turns unknown and the cache is optional.
    """

    @extend_schema(
        operation_id="ready",
        summary="Readiness",
        description=(
            "`degraded` when a circuit breaker is not closed or the cache does not answer."
        ),
        responses=ReadySerializer,
    )
    def get(self, request: Request) -> Response:
        container = get_container()
        providers = {name: state.value for name, state in container.client.breaker_states().items()}
        cache_ok = container.cache.is_reachable()
        healthy = cache_ok and all(state == BreakerState.CLOSED for state in providers.values())
        response = Response(
            {"status": "ok" if healthy else "degraded", "cache": cache_ok, "providers": providers}
        )
        response["Cache-Control"] = "no-store"
        return response


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(ErrorEnvelopeSerializer, description=description)


@method_decorator(
    ratelimit(group="plan", key="ip", rate=plan_rate, method="POST", block=True), name="post"
)
class PlanView(APIView):
    """Plan a trip: up to three routes with weather risk along each, and a recommendation."""

    @extend_schema(
        operation_id="plan",
        summary="Plan a trip",
        description=(
            "Finds up to three distinct routes between two places, forecasts the weather at "
            "each checkpoint for the time the truck gets there, ranks the routes by risk and "
            "returns the weather corridor for the 49 hours from departure. Missing weather is "
            "not an error: those places are `UNKNOWN` and the `banner` says so."
        ),
        request=PlanRequestSerializer,
        responses={
            200: PlanResponseSerializer,
            400: _error("`VALIDATION` (see `field`) or `TOO_CLOSE`."),
            422: _error("`NO_ROUTE`: no drivable route between the places."),
            429: _error("`RATE_LIMITED`."),
            502: _error("`UPSTREAM_ERROR`: a required service returned an error."),
            503: _error("`UPSTREAM_UNAVAILABLE`: a required service is down."),
            504: _error("`UPSTREAM_TIMEOUT`: a required service was too slow."),
        },
    )
    def post(self, request: Request) -> Response:
        plan_request = parse_plan_request(request.data, utc_now())
        result = get_container().plan_service.plan(plan_request)
        response = Response(present_plan(result, get_request_id(request)))
        response["Cache-Control"] = "no-store"
        return response


@method_decorator(
    ratelimit(group="geocode", key="ip", rate=geocode_rate, method="GET", block=True), name="get"
)
class GeocodeView(APIView):
    """Find places by name, for the origin and destination fields."""

    @extend_schema(
        operation_id="geocode",
        summary="Search for a place",
        description=(
            "Photon first, Nominatim when Photon fails. Answers are cached for 24 hours; "
            "no match is an empty list."
        ),
        parameters=[
            OpenApiParameter(
                "q",
                str,
                required=True,
                description=(
                    f"What to look for, {MIN_QUERY_LENGTH} to {MAX_QUERY_LENGTH} characters "
                    "once spacing is tidied."
                ),
            )
        ],
        responses={
            200: GeocodeResponseSerializer,
            400: _error("`VALIDATION`: `q` is missing, too short or too long."),
            429: _error("`RATE_LIMITED`."),
            502: _error("`UPSTREAM_ERROR`: every geocoder returned an error."),
            503: _error("`UPSTREAM_UNAVAILABLE`: every geocoder is down."),
            504: _error("`UPSTREAM_TIMEOUT`: the geocoders were too slow."),
        },
    )
    def get(self, request: Request) -> Response:
        try:
            query = normalize_query(request.query_params.get("q", ""))
        except ValueError as error:
            raise ValidationError({"q": [str(error)]}) from error
        places = get_container().geocoder.search(query)
        return Response(
            {
                "results": [
                    {"label": p.label, "lat": p.lat, "lon": p.lon, "kind": p.kind.value}
                    for p in places
                ]
            }
        )
