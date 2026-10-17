import logging
from typing import Any

import pytest
from django.http import Http404, HttpRequest
from django.test import Client, RequestFactory
from rest_framework import exceptions
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from planner.api.errors import (
    api_exception_handler,
    first_validation_error,
    json_not_found,
    json_server_error,
)
from planner.infra.errors import (
    UpstreamContractError,
    UpstreamError,
    UpstreamTimeout,
    UpstreamUnavailable,
    UpstreamWaitTimeout,
)
from planner.providers.protocols import NoRoute
from planner.services.models import TooClose


def context(request_id: str = "req-1") -> dict[str, Any]:
    django_request = APIRequestFactory().post("/api/plan", {}, format="json")
    django_request.request_id = request_id  # type: ignore[attr-defined]
    return {"request": Request(django_request)}


def handle(exc: Exception, request_id: str = "req-1") -> Any:  # noqa: ANN401
    return api_exception_handler(exc, context(request_id))


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (TooClose("secret detail"), 400, "TOO_CLOSE"),
        (NoRoute("secret detail"), 422, "NO_ROUTE"),
        (UpstreamTimeout("osrm", "secret detail"), 504, "UPSTREAM_TIMEOUT"),
        (UpstreamWaitTimeout("osrm", "secret detail"), 504, "UPSTREAM_TIMEOUT"),
        (UpstreamUnavailable("osrm", "secret detail"), 503, "UPSTREAM_UNAVAILABLE"),
        (UpstreamError("osrm", "secret detail", status=400), 502, "UPSTREAM_ERROR"),
        (UpstreamContractError("osrm", "secret detail"), 502, "UPSTREAM_ERROR"),
        (exceptions.Throttled(), 429, "RATE_LIMITED"),
        (Http404("secret detail"), 404, "NOT_FOUND"),
        (exceptions.NotFound(), 404, "NOT_FOUND"),
        (exceptions.MethodNotAllowed("PUT"), 405, "METHOD_NOT_ALLOWED"),
        (exceptions.NotAcceptable(), 406, "NOT_ACCEPTABLE"),
        (exceptions.UnsupportedMediaType("text/plain"), 415, "UNSUPPORTED_MEDIA_TYPE"),
        (exceptions.PermissionDenied(), 403, "PERMISSION_DENIED"),
        (exceptions.ParseError("JSON parse error - Expecting value"), 400, "VALIDATION"),
        (RuntimeError("secret detail"), 500, "INTERNAL_ERROR"),
        (KeyError("secret detail"), 500, "INTERNAL_ERROR"),
    ],
    ids=lambda value: type(value).__name__ if isinstance(value, Exception) else str(value),
)
def test_each_failure_has_its_status_and_code(exc: Exception, status: int, code: str) -> None:
    response = handle(exc)

    assert response.status_code == status
    assert response.data["error"]["code"] == code


def test_the_envelope_has_exactly_the_agreed_keys() -> None:
    response = handle(NoRoute("x"), request_id="trace-9")

    assert response.data == {
        "error": {
            "code": "NO_ROUTE",
            "message": "No drivable route was found between these places",
            "field": None,
            "request_id": "trace-9",
        }
    }


@pytest.mark.parametrize(
    "exc",
    [
        TooClose("secret detail 39.7392,-104.9903"),
        NoRoute("secret detail 39.7392,-104.9903"),
        UpstreamTimeout("osrm", "secret detail 39.7392,-104.9903"),
        UpstreamUnavailable("osrm", "secret detail 39.7392,-104.9903"),
        UpstreamContractError("osrm", "secret detail 39.7392,-104.9903"),
        RuntimeError("secret detail 39.7392,-104.9903"),
    ],
    ids=lambda exc: type(exc).__name__,
)
def test_messages_never_carry_exception_text(exc: Exception) -> None:
    message = handle(exc).data["error"]["message"]

    assert "secret" not in message
    assert "39.7392" not in message


def test_an_unexpected_error_is_logged_with_its_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR):
        handle(RuntimeError("boom"))

    assert "unhandled error in a view" in caplog.text
    assert "boom" in caplog.text  # in the log, not in the response


def test_an_upstream_failure_is_logged_without_its_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        handle(UpstreamUnavailable("osrm", "details with 39.7392,-104.9903"))

    assert "upstream failure from osrm (UpstreamUnavailable)" in caplog.text
    assert "39.7392" not in caplog.text


def test_a_throttled_response_says_when_to_retry() -> None:
    response = handle(exceptions.Throttled(wait=29.2))

    assert response["Retry-After"] == "30"


def test_a_retry_after_is_never_zero() -> None:
    assert handle(exceptions.Throttled(wait=0))["Retry-After"] == "1"


def test_an_unparseable_body_gets_a_fixed_message_not_the_parsers() -> None:
    error = handle(
        exceptions.ParseError("JSON parse error - Expecting value: line 1 column 1")
    ).data["error"]

    assert error["message"] == "The request body is not valid JSON"
    assert error["field"] is None


def test_a_throttled_response_without_a_wait_has_no_retry_after() -> None:
    assert "Retry-After" not in handle(exceptions.Throttled())


def test_outside_the_middleware_the_request_id_is_empty() -> None:
    response = api_exception_handler(NoRoute("x"), {"request": None})

    assert response.data["error"]["request_id"] == ""


class TestValidationErrors:
    def test_a_field_error_names_the_field(self) -> None:
        response = handle(exceptions.ValidationError({"load_lb": ["Must be at least 0."]}))

        assert response.status_code == 400
        assert response.data["error"] == {
            "code": "VALIDATION",
            "message": "Must be at least 0.",
            "field": "load_lb",
            "request_id": "req-1",
        }

    def test_a_nested_error_names_the_dotted_path(self) -> None:
        detail = {"origin": {"lat": ["Ensure this value is less than or equal to 90."]}}

        assert first_validation_error(exceptions.ValidationError(detail).detail) == (
            "origin.lat",
            "Ensure this value is less than or equal to 90.",
        )

    def test_the_first_error_wins(self) -> None:
        detail = {"origin": ["first"], "load_lb": ["second"]}

        assert first_validation_error(exceptions.ValidationError(detail).detail) == (
            "origin",
            "first",
        )

    def test_a_non_field_error_has_no_field(self) -> None:
        detail = {"non_field_errors": ["Something is off."]}

        assert first_validation_error(exceptions.ValidationError(detail).detail) == (
            None,
            "Something is off.",
        )

    def test_a_non_field_error_inside_a_field_keeps_the_field(self) -> None:
        detail = {"origin": {"non_field_errors": ["Bad point."]}}

        assert first_validation_error(exceptions.ValidationError(detail).detail) == (
            "origin",
            "Bad point.",
        )

    def test_a_plain_list_has_no_field(self) -> None:
        assert first_validation_error(exceptions.ValidationError(["Bad body."]).detail) == (
            None,
            "Bad body.",
        )

    def test_a_plain_message_has_no_field(self) -> None:
        assert first_validation_error(exceptions.ValidationError("Bad body.").detail) == (
            None,
            "Bad body.",
        )

    def test_nothing_to_report(self) -> None:
        assert first_validation_error({}) == (None, "")
        assert first_validation_error([]) == (None, "")

    def test_empty_items_in_a_list_are_skipped(self) -> None:
        assert first_validation_error(["", "Real error."]) == (None, "Real error.")

    @pytest.mark.parametrize("detail", ["", None, 0])
    def test_an_empty_value_has_nothing_to_report(self, detail: object) -> None:
        assert first_validation_error(detail) == (None, "")

    def test_errors_inside_a_list_of_objects_name_the_parent_field(self) -> None:
        detail = {"waypoints": [{}, {"lat": ["Out of range."]}]}

        assert first_validation_error(detail) == ("waypoints.lat", "Out of range.")

    def test_empty_inner_errors_are_skipped(self) -> None:
        detail = {"origin": [], "load_lb": ["Real error."]}

        assert first_validation_error(detail) == ("load_lb", "Real error.")


class TestFrameworkErrors:
    def test_an_unknown_url_is_a_json_envelope(self) -> None:
        response = Client().get("/api/nothing-here", headers={"X-Request-ID": "trace-3"})

        assert response.status_code == 404
        assert response["Content-Type"] == "application/json"
        assert response.json()["error"] == {
            "code": "NOT_FOUND",
            "message": "There is nothing at this address",
            "field": None,
            "request_id": "trace-3",
        }

    def test_the_wrong_method_is_a_json_envelope(self) -> None:
        response = Client().post("/api/health", headers={"X-Request-ID": "trace-4"})

        assert response.status_code == 405
        assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
        assert response.json()["error"]["request_id"] == "trace-4"

    def test_a_failure_outside_the_views_is_a_json_envelope(self) -> None:
        request: HttpRequest = RequestFactory().get("/")
        request.request_id = "trace-5"  # type: ignore[attr-defined]

        response = json_server_error(request)

        assert response.status_code == 500
        assert response["Content-Type"] == "application/json"
        assert b'"INTERNAL_ERROR"' in response.content
        assert b'"trace-5"' in response.content

    def test_the_not_found_handler_works_on_its_own(self) -> None:
        request = RequestFactory().get("/missing")

        response = json_not_found(request, Http404())

        assert response.status_code == 404
        assert b'"NOT_FOUND"' in response.content
