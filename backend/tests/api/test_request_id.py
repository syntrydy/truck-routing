import re

import pytest
from django.http import HttpRequest, HttpResponse
from django.test import Client

from planner.api.middleware import RequestIdMiddleware, get_request_id

HEX_32 = re.compile(r"[0-9a-f]{32}")


@pytest.fixture
def client() -> Client:
    return Client()


def test_a_request_without_an_id_gets_a_generated_one(client: Client) -> None:
    response = client.get("/api/health")

    assert HEX_32.fullmatch(response["X-Request-ID"])


def test_every_request_gets_a_different_generated_id(client: Client) -> None:
    ids = {client.get("/api/health")["X-Request-ID"] for _ in range(5)}

    assert len(ids) == 5


@pytest.mark.parametrize("given", ["abc-123", "A.b_c-9", "a", "x" * 64, "0123456789abcdef"])
def test_a_sane_incoming_id_is_kept_and_echoed(client: Client, given: str) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": given})

    assert response["X-Request-ID"] == given


@pytest.mark.parametrize(
    "given",
    ["has space", "x" * 65, "a/b", "a;b", "ünï", "a\tb", "<script>", "../etc", "a,b", "id "],
)
def test_an_unsafe_or_overlong_id_is_replaced(client: Client, given: str) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": given})

    assert response["X-Request-ID"] != given
    assert HEX_32.fullmatch(response["X-Request-ID"])


def test_an_empty_id_is_replaced(client: Client) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": ""})

    assert HEX_32.fullmatch(response["X-Request-ID"])


def test_the_id_is_on_error_responses_too(client: Client) -> None:
    missing = client.get("/api/nothing-here", headers={"X-Request-ID": "trace-1"})
    wrong_method = client.post("/api/health", headers={"X-Request-ID": "trace-2"})

    assert missing.status_code == 404
    assert missing["X-Request-ID"] == "trace-1"
    assert wrong_method.status_code == 405
    assert wrong_method["X-Request-ID"] == "trace-2"


def test_the_id_is_available_to_the_view_as_an_attribute() -> None:
    seen: list[str] = []

    def view(request: HttpRequest) -> HttpResponse:
        seen.append(get_request_id(request))
        return HttpResponse("ok")

    request = HttpRequest()
    request.META["HTTP_X_REQUEST_ID"] = "inside-1"

    RequestIdMiddleware(view)(request)

    assert seen == ["inside-1"]


def test_outside_the_middleware_there_is_no_id() -> None:
    assert get_request_id(HttpRequest()) == ""
