"""Request IDs (SPEC section 9): accepted when sane, generated otherwise, always echoed."""

import re
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

REQUEST_ID_HEADER = "X-Request-ID"
# What a caller may send as an ID: short, printable and free of anything a log could mistake.
VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


def get_request_id(request: object) -> str:
    """The ID of a Django or DRF ``request``; empty outside the middleware."""
    return str(getattr(request, "request_id", ""))


class RequestIdMiddleware:
    """Gives every request an ID, available as ``request.request_id`` and in the response."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self._get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if VALID_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        request.request_id = request_id  # type: ignore[attr-defined]
        response = self._get_response(request)
        response[REQUEST_ID_HEADER] = request_id
        return response
