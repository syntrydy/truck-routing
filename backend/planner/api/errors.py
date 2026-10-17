"""The single error shape of the API and the mapping of failures onto it (SPEC section 5).

Every error body is ``{"error": {"code", "message", "field", "request_id"}}``. Messages are
fixed, human-readable sentences: they never carry exception text, provider details or
coordinates.
"""

import logging
import math
from typing import Any

from django.http import Http404, HttpRequest, JsonResponse
from rest_framework import exceptions
from rest_framework.response import Response

from planner.api.middleware import get_request_id
from planner.infra.errors import UpstreamError, UpstreamTimeout, UpstreamUnavailable
from planner.providers.protocols import NoRoute
from planner.services.models import TooClose

logger = logging.getLogger(__name__)

HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERROR = 500
HTTP_BAD_GATEWAY = 502
HTTP_UNAVAILABLE = 503
HTTP_GATEWAY_TIMEOUT = 504

MESSAGES = {
    "TOO_CLOSE": "Origin and destination must be at least 1 mile apart",
    "NO_ROUTE": "No drivable route was found between these places",
    "RATE_LIMITED": "Too many requests; please slow down",
    "UPSTREAM_ERROR": "A required service returned an error",
    "UPSTREAM_UNAVAILABLE": "A required service is currently unavailable",
    "UPSTREAM_TIMEOUT": "A required service took too long to respond",
    "INTERNAL_ERROR": "Something went wrong on our side",
    "NOT_FOUND": "There is nothing at this address",
}


def error_body(
    code: str, message: str, request_id: str, field: str | None = None
) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "field": field, "request_id": request_id}}


def error_response(
    status: int, code: str, message: str, request: object, field: str | None = None
) -> Response:
    return Response(error_body(code, message, get_request_id(request), field), status=status)


# Failures with a fixed answer, checked in order: the specific upstream errors come before
# their base class.
FIXED_ERRORS: tuple[tuple[type[Exception], int, str], ...] = (
    (TooClose, HTTP_BAD_REQUEST, "TOO_CLOSE"),
    (NoRoute, HTTP_UNPROCESSABLE, "NO_ROUTE"),
    (UpstreamTimeout, HTTP_GATEWAY_TIMEOUT, "UPSTREAM_TIMEOUT"),
    (UpstreamUnavailable, HTTP_UNAVAILABLE, "UPSTREAM_UNAVAILABLE"),
    (UpstreamError, HTTP_BAD_GATEWAY, "UPSTREAM_ERROR"),
    (exceptions.Throttled, HTTP_TOO_MANY_REQUESTS, "RATE_LIMITED"),
    (Http404, HTTP_NOT_FOUND, "NOT_FOUND"),
)


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    """Turn any exception raised by a view into an error envelope."""
    request = context.get("request")
    status, code, message, field = _describe(exc)
    response = error_response(status, code, message, request, field)
    wait = getattr(exc, "wait", None) if isinstance(exc, exceptions.Throttled) else None
    if wait is not None:
        response["Retry-After"] = str(max(1, math.ceil(wait)))
    return response


def _describe(exc: Exception) -> tuple[int, str, str, str | None]:
    """The status, code, message and field of the error envelope for ``exc``."""
    if isinstance(exc, UpstreamError):
        logger.warning("upstream failure from %s (%s)", exc.provider, type(exc).__name__)
    for error_type, status, code in FIXED_ERRORS:
        if isinstance(exc, error_type):
            return status, code, MESSAGES[code], None
    if isinstance(exc, exceptions.ValidationError):
        field, message = first_validation_error(exc.detail)
        return HTTP_BAD_REQUEST, "VALIDATION", message, field
    if isinstance(exc, exceptions.ParseError):
        return HTTP_BAD_REQUEST, "VALIDATION", "The request body is not valid JSON", None
    if isinstance(exc, exceptions.APIException):
        return exc.status_code, exc.default_code.upper(), str(exc.detail), None
    # Our bug: log it with its traceback and tell the caller nothing more.
    logger.error("unhandled error in a view", exc_info=exc)
    return HTTP_SERVER_ERROR, "INTERNAL_ERROR", MESSAGES["INTERNAL_ERROR"], None


def first_validation_error(detail: object, path: tuple[str, ...] = ()) -> tuple[str | None, str]:
    """The first message in a DRF validation error, with the dotted path of its field."""
    if isinstance(detail, dict):
        for key, value in detail.items():
            found = first_validation_error(
                value, path if key == "non_field_errors" else (*path, str(key))
            )
            if found[1]:
                return found
    elif isinstance(detail, list):
        for item in detail:
            found = first_validation_error(item, path)
            if found[1]:
                return found
    elif detail:
        return (".".join(path) or None), str(detail)
    return None, ""


def json_not_found(request: HttpRequest, exception: Exception) -> JsonResponse:
    """Django's 404 for an unknown URL, in the error shape."""
    body = error_body("NOT_FOUND", MESSAGES["NOT_FOUND"], get_request_id(request))
    return JsonResponse(body, status=HTTP_NOT_FOUND)


def json_server_error(request: HttpRequest) -> JsonResponse:
    """Django's 500 for a failure outside the views, in the error shape."""
    body = error_body("INTERNAL_ERROR", MESSAGES["INTERNAL_ERROR"], get_request_id(request))
    return JsonResponse(body, status=HTTP_SERVER_ERROR)
