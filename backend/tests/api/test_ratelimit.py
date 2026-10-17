import time
from typing import Any

import pytest
from django.core.cache import cache
from django.http import HttpRequest
from django.test import RequestFactory
from rest_framework.test import APIClient

from config import settings as project_settings
from planner.api.ratelimit import RETRY_AFTER_S, UNKNOWN_ADDRESS, client_ip, geocode_rate, plan_rate
from tests.api.helpers import three_routes, valid_body
from tests.services.stubs import StubRouting


def request_from(remote: str = "203.0.113.9", forwarded: str | None = None) -> HttpRequest:
    request = RequestFactory().get("/")
    request.META["REMOTE_ADDR"] = remote
    if forwarded is not None:
        request.META["HTTP_X_FORWARDED_FOR"] = forwarded
    return request


class TestClientAddress:
    def test_without_a_trusted_proxy_it_is_the_connections_address(self, settings: Any) -> None:
        settings.TRUSTED_PROXY_COUNT = 0

        assert client_ip(request_from("203.0.113.9")) == "203.0.113.9"

    def test_without_a_trusted_proxy_the_forwarded_header_is_ignored(self, settings: Any) -> None:
        settings.TRUSTED_PROXY_COUNT = 0

        assert client_ip(request_from("203.0.113.9", forwarded="1.1.1.1")) == "203.0.113.9"

    def test_with_one_proxy_the_last_entry_is_the_client(self, settings: Any) -> None:
        settings.TRUSTED_PROXY_COUNT = 1

        assert client_ip(request_from("10.0.0.1", forwarded="198.51.100.7")) == "198.51.100.7"

    def test_what_the_client_put_in_front_of_it_is_ignored(self, settings: Any) -> None:
        settings.TRUSTED_PROXY_COUNT = 1

        forged = "6.6.6.6, 7.7.7.7, 198.51.100.7"

        assert client_ip(request_from("10.0.0.1", forwarded=forged)) == "198.51.100.7"

    def test_with_two_proxies_the_second_from_the_right_is_the_client(self, settings: Any) -> None:
        settings.TRUSTED_PROXY_COUNT = 2

        forwarded = "9.9.9.9, 198.51.100.7, 10.0.0.2"

        assert client_ip(request_from("10.0.0.1", forwarded=forwarded)) == "198.51.100.7"

    @pytest.mark.parametrize("forwarded", [None, "", "not-an-address", "198.51.100.7"])
    def test_a_header_that_is_too_short_or_not_an_address_falls_back(
        self, settings: Any, forwarded: str | None
    ) -> None:
        settings.TRUSTED_PROXY_COUNT = 2

        assert client_ip(request_from("203.0.113.9", forwarded=forwarded)) == "203.0.113.9"

    @pytest.mark.parametrize(
        "forwarded", ["garbage", "1.1.1.1, garbage", "1.1.1.1, 999.1.1.1", "1.1.1.1, "]
    )
    def test_a_last_entry_that_is_not_an_address_falls_back(
        self, settings: Any, forwarded: str
    ) -> None:
        settings.TRUSTED_PROXY_COUNT = 1

        assert client_ip(request_from("203.0.113.9", forwarded=forwarded)) == "203.0.113.9"

    def test_ipv6_addresses_are_accepted(self, settings: Any) -> None:
        settings.TRUSTED_PROXY_COUNT = 1

        assert client_ip(request_from("10.0.0.1", forwarded="2001:db8::1")) == "2001:db8::1"

    def test_spaces_around_entries_are_tolerated(self, settings: Any) -> None:
        settings.TRUSTED_PROXY_COUNT = 2

        assert client_ip(
            request_from("10.0.0.1", forwarded="1.1.1.1 ,  198.51.100.7 ,10.0.0.2")
        ) == ("198.51.100.7")

    @pytest.mark.parametrize("remote", ["", "unix-socket", "999.1.1.1"])
    def test_an_unusable_connection_address_shares_one_bucket(
        self, settings: Any, remote: str
    ) -> None:
        settings.TRUSTED_PROXY_COUNT = 0

        assert client_ip(request_from(remote)) == UNKNOWN_ADDRESS

    def test_a_missing_connection_address_shares_one_bucket(self, settings: Any) -> None:
        settings.TRUSTED_PROXY_COUNT = 0
        request = RequestFactory().get("/")
        request.META.pop("REMOTE_ADDR", None)

        assert client_ip(request) == UNKNOWN_ADDRESS


class TestDefaults:
    """The defaults of the project's own settings, which the test settings override."""

    def test_no_proxy_is_trusted_unless_configured(self) -> None:
        assert project_settings.TRUSTED_PROXY_COUNT == 0

    def test_rate_limiting_is_on_unless_switched_off(self) -> None:
        assert project_settings.RATELIMIT_ENABLE is True
        assert project_settings.PLAN_RATE_LIMIT == "10/m"
        assert project_settings.GEOCODE_RATE_LIMIT == "60/m"

    def test_the_limiter_counts_in_the_default_cache_with_our_address_lookup(self) -> None:
        assert project_settings.RATELIMIT_USE_CACHE == "default"
        assert project_settings.RATELIMIT_IP_META_KEY == "planner.api.ratelimit.client_ip"


class TestConfiguredRates:
    def test_the_defaults_follow_the_spec(self, settings: Any) -> None:
        request = request_from()

        assert plan_rate("plan", request) == settings.PLAN_RATE_LIMIT == "10/m"
        assert geocode_rate("geocode", request) == settings.GEOCODE_RATE_LIMIT == "60/m"

    def test_the_rates_are_read_when_a_request_arrives(self, settings: Any) -> None:
        settings.PLAN_RATE_LIMIT = "2/m"
        settings.GEOCODE_RATE_LIMIT = "5/h"

        assert plan_rate("plan", request_from()) == "2/m"
        assert geocode_rate("geocode", request_from()) == "5/h"


@pytest.fixture
def limited(settings: Any, monkeypatch: pytest.MonkeyPatch) -> Any:  # noqa: ANN401
    """Switch the limiter on with an empty cache and a clock in the middle of a window."""
    window_middle = 1_800_000_030.0
    monkeypatch.setattr(time, "time", lambda: window_middle)
    settings.RATELIMIT_ENABLE = True
    settings.TRUSTED_PROXY_COUNT = 0
    cache.clear()
    yield
    cache.clear()


def post_plan(client: APIClient, remote: str = "203.0.113.9", **extra: Any) -> Any:  # noqa: ANN401
    return client.post("/api/plan", data=valid_body(), format="json", REMOTE_ADDR=remote, **extra)


class TestPlanLimit:
    def test_ten_requests_a_minute_are_allowed_and_the_eleventh_is_not(
        self,
        limited: Any,
        install: Any,
    ) -> None:
        install()
        client = APIClient()

        statuses = [post_plan(client).status_code for _ in range(11)]

        assert statuses == [200] * 10 + [429]

    def test_the_refusal_is_the_json_envelope_with_retry_after(
        self,
        limited: Any,
        install: Any,
    ) -> None:
        install()
        client = APIClient()
        for _ in range(10):
            post_plan(client)

        response = post_plan(client, headers={"X-Request-ID": "trace-9"})

        assert response.status_code == 429
        assert response["Content-Type"] == "application/json"
        assert response["Retry-After"] == str(RETRY_AFTER_S) == "60"
        assert response.json()["error"] == {
            "code": "RATE_LIMITED",
            "message": "Too many requests; please slow down",
            "field": None,
            "request_id": "trace-9",
        }
        assert response["X-Request-ID"] == "trace-9"

    def test_each_client_has_its_own_count(self, limited: Any, install: Any) -> None:
        install()
        client = APIClient()
        for _ in range(10):
            post_plan(client, "203.0.113.9")

        assert post_plan(client, "203.0.113.9").status_code == 429
        assert post_plan(client, "198.51.100.1").status_code == 200

    def test_invalid_requests_count_too(self, limited: Any, install: Any) -> None:
        install()
        client = APIClient()

        for _ in range(10):
            response = client.post("/api/plan", data={}, format="json", REMOTE_ADDR="203.0.113.9")
            assert response.status_code == 400

        assert post_plan(client).status_code == 429

    def test_a_refused_request_never_reaches_the_service(
        self,
        limited: Any,
        install: Any,
    ) -> None:
        routing = StubRouting(three_routes())
        install(routing)
        client = APIClient()
        for _ in range(10):
            post_plan(client)
        calls_before = len(routing.calls)

        post_plan(client)

        assert len(routing.calls) == calls_before

    def test_the_limit_can_be_changed_by_setting(
        self,
        limited: Any,
        install: Any,
        settings: Any,
    ) -> None:
        install()
        settings.PLAN_RATE_LIMIT = "2/m"
        client = APIClient()

        statuses = [post_plan(client).status_code for _ in range(3)]

        assert statuses == [200, 200, 429]

    def test_the_count_starts_again_in_the_next_minute(
        self,
        limited: Any,
        install: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        install()
        client = APIClient()
        for _ in range(10):
            post_plan(client)
        assert post_plan(client).status_code == 429

        monkeypatch.setattr(time, "time", lambda: 1_800_000_030.0 + 125)

        assert post_plan(client).status_code == 200

    def test_a_forged_forwarded_header_does_not_dodge_the_limit(
        self,
        limited: Any,
        install: Any,
        settings: Any,
    ) -> None:
        install()
        settings.TRUSTED_PROXY_COUNT = 1
        client = APIClient()

        statuses = [
            post_plan(
                client, "10.0.0.1", HTTP_X_FORWARDED_FOR=f"{n}.{n}.{n}.{n}, 198.51.100.7"
            ).status_code
            for n in range(1, 12)
        ]

        assert statuses == [200] * 10 + [429]

    def test_without_a_trusted_proxy_a_forged_header_does_not_help_either(
        self,
        limited: Any,
        install: Any,
    ) -> None:
        install()
        client = APIClient()

        statuses = [
            post_plan(client, HTTP_X_FORWARDED_FOR=f"{n}.{n}.{n}.{n}").status_code
            for n in range(1, 12)
        ]

        assert statuses == [200] * 10 + [429]

    def test_clients_behind_the_same_proxy_are_counted_separately(
        self,
        limited: Any,
        install: Any,
        settings: Any,
    ) -> None:
        install()
        settings.TRUSTED_PROXY_COUNT = 1
        client = APIClient()
        for _ in range(10):
            post_plan(client, "10.0.0.1", HTTP_X_FORWARDED_FOR="198.51.100.7")

        assert post_plan(client, "10.0.0.1", HTTP_X_FORWARDED_FOR="198.51.100.7").status_code == 429
        assert post_plan(client, "10.0.0.1", HTTP_X_FORWARDED_FOR="198.51.100.8").status_code == 200

    def test_ipv6_clients_in_one_network_share_a_count(self, limited: Any, install: Any) -> None:
        install()
        client = APIClient()
        for number in range(10):
            post_plan(client, f"2001:db8:1:2::{number + 1}")

        assert post_plan(client, "2001:db8:1:2:ffff::1").status_code == 429
        assert post_plan(client, "2001:db8:1:3::1").status_code == 200

    def test_switching_the_limiter_off_removes_the_limit(
        self,
        install: Any,
        settings: Any,
    ) -> None:
        install()
        settings.RATELIMIT_ENABLE = False
        client = APIClient()

        assert all(post_plan(client).status_code == 200 for _ in range(15))

    def test_other_endpoints_are_not_limited(self, limited: Any) -> None:
        client = APIClient()

        assert all(client.get("/api/health").status_code == 200 for _ in range(30))
        assert all(client.get("/api/schema/").status_code == 200 for _ in range(15))

    def test_other_methods_are_not_counted(self, limited: Any, install: Any) -> None:
        install()
        client = APIClient()
        for _ in range(15):
            assert client.get("/api/plan").status_code == 405

        assert post_plan(client).status_code == 200
