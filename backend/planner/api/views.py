"""API views."""

from datetime import UTC, datetime

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from planner.api.middleware import get_request_id
from planner.api.presenters import present_plan
from planner.api.serializers import (
    ErrorEnvelopeSerializer,
    HealthSerializer,
    PlanRequestSerializer,
    PlanResponseSerializer,
    parse_plan_request,
)
from planner.services.container import get_container


def utc_now() -> datetime:
    """The current time; a function so that tests can fix it."""
    return datetime.now(UTC)


class HealthView(APIView):
    """Liveness probe. Makes no upstream calls."""

    @extend_schema(responses=HealthSerializer, operation_id="health")
    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(ErrorEnvelopeSerializer, description=description)


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
