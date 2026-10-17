from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx

from planner.infra.errors import (
    HostNotAllowed,
    UpstreamContractError,
    UpstreamError,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from planner.infra.http import (
    ProviderPolicy,
    UpstreamClient,
    default_policies,
    upstream_client_from_settings,
)
from planner.infra.resilience import Deadline, MinSpacing, deadline_scope
from tests.infra.fakes import FakeClock, FixedJitter

OSRM_URL = "https://router.project-osrm.org/route/v1/driving/-104.99,39.74;-87.63,41.88"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "TruckRoutingTests/1.0 (+https://example.test)"
ALLOWED = ["router.project-osrm.org", "api.open-meteo.com"]
OK = {"code": "Ok"}


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def make_client(
    clock: FakeClock, jitter: FixedJitter | None = None, **overrides: object
) -> UpstreamClient:
    policies = [
        ProviderPolicy("osrm", timeout_s=8.0, max_concurrency=1),
        ProviderPolicy("open-meteo", timeout_s=10.0, max_concurrency=4),
    ]
    return UpstreamClient(
        policies,
        ALLOWED,
        USER_AGENT,
        clock=clock,
        sleep=clock.sleep,
        jitter=jitter or FixedJitter(1.0),
        **overrides,  # type: ignore[arg-type]
    )


class TestSuccess:
    def test_returns_the_response_and_sends_the_user_agent(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = api.get(OSRM_URL).respond(200, json=OK)

        response = make_client(clock).get("osrm", OSRM_URL)

        assert response.json() == OK
        assert route.calls.last.request.headers["User-Agent"] == USER_AGENT

    def test_query_parameters_are_encoded_by_the_http_library(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = api.get(WEATHER_URL).respond(200, json={})

        make_client(clock).get("open-meteo", WEATHER_URL, params={"q": "a b&c=d", "n": 3})

        assert route.calls.last.request.url.query == b"q=a+b%26c%3Dd&n=3"

    def test_get_json_decodes_the_body(self, api: respx.MockRouter, clock: FakeClock) -> None:
        api.get(OSRM_URL).respond(200, json=OK)

        assert make_client(clock).get_json("osrm", OSRM_URL) == OK

    def test_get_json_rejects_a_body_that_is_not_json(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        api.get(OSRM_URL).respond(200, text="<html>maintenance</html>")

        with pytest.raises(UpstreamContractError, match="not valid JSON"):
            make_client(clock).get_json("osrm", OSRM_URL)

    def test_unknown_provider_is_a_programming_error(self, clock: FakeClock) -> None:
        with pytest.raises(ValueError, match="unknown provider"):
            make_client(clock).get("mapbox", OSRM_URL)


class TestTimeouts:
    def test_uses_the_provider_timeout_without_a_deadline(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = api.get(OSRM_URL).respond(200, json=OK)

        make_client(clock).get("osrm", OSRM_URL)

        timeout = route.calls.last.request.extensions["timeout"]
        assert timeout["read"] == 8.0
        assert timeout["connect"] == 3.0

    def test_a_read_timeout_is_reported_and_not_retried(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = api.get(OSRM_URL).mock(side_effect=httpx.ReadTimeout("slow"))

        with pytest.raises(UpstreamTimeout, match="timed out"):
            make_client(clock).get("osrm", OSRM_URL)

        assert route.call_count == 1
        assert clock.sleeps == []

    def test_each_call_gets_the_smaller_of_its_timeout_and_the_remaining_budget(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = api.get(OSRM_URL).respond(200, json=OK)
        deadline = Deadline(20.0, clock)
        clock.advance(18.0)

        make_client(clock).get("osrm", OSRM_URL, deadline=deadline)

        timeout = route.calls.last.request.extensions["timeout"]
        assert timeout["read"] == pytest.approx(2.0)
        assert timeout["connect"] == pytest.approx(2.0)

    def test_a_generous_budget_leaves_the_provider_timeout_alone(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = api.get(OSRM_URL).respond(200, json=OK)

        make_client(clock).get("osrm", OSRM_URL, deadline=Deadline(20.0, clock))

        assert route.calls.last.request.extensions["timeout"]["read"] == 8.0

    def test_an_exhausted_deadline_stops_the_call_before_any_request(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = api.get(OSRM_URL).respond(200, json=OK)
        deadline = Deadline(20.0, clock)
        clock.advance(20.0)

        with pytest.raises(UpstreamTimeout, match="deadline"):
            make_client(clock).get("osrm", OSRM_URL, deadline=deadline)

        assert not route.called

    def test_the_deadline_of_the_enclosing_scope_applies(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = api.get(OSRM_URL).respond(200, json=OK)
        client = make_client(clock)

        with deadline_scope(5.0, clock):
            clock.advance(6.0)
            with pytest.raises(UpstreamTimeout, match="deadline"):
                client.get("osrm", OSRM_URL)

        assert not route.called

    def test_running_out_of_budget_does_not_count_against_the_provider(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        api.get(OSRM_URL).respond(200, json=OK)
        client = make_client(clock)
        spent = Deadline(1.0, clock)
        clock.advance(2.0)

        for _ in range(5):
            with pytest.raises(UpstreamTimeout):
                client.get("osrm", OSRM_URL, deadline=spent)

        assert client.get("osrm", OSRM_URL).json() == OK

    def test_a_sleep_that_overshoots_the_budget_ends_with_the_last_failure(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = api.get(OSRM_URL).respond(503)

        def slow_sleep(seconds: float) -> None:
            clock.advance(seconds + 5.0)  # the real sleep took far longer than asked

        client = UpstreamClient(
            [ProviderPolicy("osrm", timeout_s=8.0, max_concurrency=1)],
            ALLOWED,
            USER_AGENT,
            clock=clock,
            sleep=slow_sleep,
            jitter=FixedJitter(1.0),
        )

        with pytest.raises(UpstreamUnavailable, match="503"):
            client.get("osrm", OSRM_URL, deadline=Deadline(1.0, clock))

        assert route.call_count == 1

    def test_no_time_to_back_off_gives_up_with_the_last_failure(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = api.get(OSRM_URL).respond(503)
        deadline = Deadline(0.2, clock)

        with pytest.raises(UpstreamUnavailable, match="503"):
            make_client(clock, FixedJitter(1.0)).get("osrm", OSRM_URL, deadline=deadline)

        assert route.call_count == 1
        assert clock.sleeps == []


class TestRetries:
    def test_retries_once_on_a_server_error_then_succeeds(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = api.get(OSRM_URL).mock(
            side_effect=[httpx.Response(503), httpx.Response(200, json=OK)]
        )
        jitter = FixedJitter(0.5)

        response = make_client(clock, jitter).get("osrm", OSRM_URL)

        assert response.json() == OK
        assert route.call_count == 2
        assert jitter.calls == [(0.0, 0.3)]
        assert clock.sleeps == [pytest.approx(0.15)]

    def test_backoff_is_full_jitter_up_to_the_base_delay(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        api.get(OSRM_URL).mock(side_effect=[httpx.Response(500), httpx.Response(200, json=OK)])
        jitter = FixedJitter(1.0)

        make_client(clock, jitter).get("osrm", OSRM_URL)

        assert clock.sleeps == [pytest.approx(0.3)]

    def test_retries_when_rate_limited(self, api: respx.MockRouter, clock: FakeClock) -> None:
        route = api.get(OSRM_URL).mock(
            side_effect=[httpx.Response(429), httpx.Response(200, json=OK)]
        )

        make_client(clock).get("osrm", OSRM_URL)

        assert route.call_count == 2

    @pytest.mark.parametrize(
        "failure",
        [
            httpx.ConnectError("refused"),
            httpx.ConnectTimeout("no route"),
            httpx.RemoteProtocolError("reset"),
        ],
        ids=["connect-error", "connect-timeout", "protocol-error"],
    )
    def test_retries_connection_failures(
        self, api: respx.MockRouter, clock: FakeClock, failure: Exception
    ) -> None:
        route = api.get(OSRM_URL).mock(side_effect=[failure, httpx.Response(200, json=OK)])

        make_client(clock).get("osrm", OSRM_URL)

        assert route.call_count == 2

    def test_gives_up_after_one_retry_with_unavailable(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = api.get(OSRM_URL).respond(502)

        with pytest.raises(UpstreamUnavailable, match="502"):
            make_client(clock).get("osrm", OSRM_URL)

        assert route.call_count == 2

    def test_connection_failures_end_as_unavailable(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        api.get(OSRM_URL).mock(side_effect=httpx.ConnectError("refused"))

        with pytest.raises(UpstreamUnavailable, match="cannot connect"):
            make_client(clock).get("osrm", OSRM_URL)

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
    def test_client_errors_are_not_retried(
        self, api: respx.MockRouter, clock: FakeClock, status: int
    ) -> None:
        route = api.get(OSRM_URL).respond(status)

        with pytest.raises(UpstreamError, match=str(status)) as raised:
            make_client(clock).get("osrm", OSRM_URL)

        assert type(raised.value) is UpstreamError
        assert route.call_count == 1
        assert clock.sleeps == []

    def test_redirects_are_not_followed(self, api: respx.MockRouter, clock: FakeClock) -> None:
        api.get(OSRM_URL).respond(302, headers={"Location": "https://evil.example/"})

        with pytest.raises(UpstreamError, match="302"):
            make_client(clock).get("osrm", OSRM_URL)


class TestCircuitBreaker:
    def fail_three_calls(self, api: respx.MockRouter, client: UpstreamClient) -> respx.Route:
        route = api.get(OSRM_URL).respond(503)
        for _ in range(3):
            with pytest.raises(UpstreamUnavailable, match="503"):
                client.get("osrm", OSRM_URL)
        return route

    def test_opens_after_three_failed_calls_and_stops_calling_the_provider(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        client = make_client(clock)
        route = self.fail_three_calls(api, client)
        calls_so_far = route.call_count

        with pytest.raises(UpstreamUnavailable, match="circuit open"):
            client.get("osrm", OSRM_URL)

        assert route.call_count == calls_so_far == 6  # two attempts per failed call

    def test_one_provider_failing_does_not_open_another(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        client = make_client(clock)
        self.fail_three_calls(api, client)
        api.get(WEATHER_URL).respond(200, json={})

        assert client.get("open-meteo", WEATHER_URL).status_code == 200

    def test_half_opens_after_60_seconds_and_closes_on_success(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        client = make_client(clock)
        self.fail_three_calls(api, client)
        clock.advance(59.0)
        with pytest.raises(UpstreamUnavailable, match="circuit open"):
            client.get("osrm", OSRM_URL)

        clock.advance(1.0)
        api.get(OSRM_URL).respond(200, json=OK)

        assert client.get("osrm", OSRM_URL).json() == OK
        assert client.get("osrm", OSRM_URL).json() == OK  # closed again

    def test_a_failed_probe_opens_the_breaker_again(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        client = make_client(clock)
        route = self.fail_three_calls(api, client)
        clock.advance(60.0)

        with pytest.raises(UpstreamUnavailable, match="503"):
            client.get("osrm", OSRM_URL)
        calls_after_probe = route.call_count
        with pytest.raises(UpstreamUnavailable, match="circuit open"):
            client.get("osrm", OSRM_URL)

        assert route.call_count == calls_after_probe

    def test_timeouts_count_as_failures(self, api: respx.MockRouter, clock: FakeClock) -> None:
        client = make_client(clock)
        api.get(OSRM_URL).mock(side_effect=httpx.ReadTimeout("slow"))
        for _ in range(3):
            with pytest.raises(UpstreamTimeout):
                client.get("osrm", OSRM_URL)

        with pytest.raises(UpstreamUnavailable, match="circuit open"):
            client.get("osrm", OSRM_URL)

    def test_client_errors_do_not_trip_the_breaker(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        client = make_client(clock)
        api.get(OSRM_URL).respond(400)
        for _ in range(6):
            with pytest.raises(UpstreamError):
                client.get("osrm", OSRM_URL)
        api.get(OSRM_URL).respond(200, json=OK)

        assert client.get("osrm", OSRM_URL).json() == OK

    def test_a_success_between_failures_keeps_it_closed(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        client = make_client(clock)
        route = api.get(OSRM_URL)
        for _ in range(2):
            route.respond(503)
            with pytest.raises(UpstreamUnavailable):
                client.get("osrm", OSRM_URL)
        route.respond(200, json=OK)
        client.get("osrm", OSRM_URL)
        route.respond(503)
        for _ in range(2):
            with pytest.raises(UpstreamUnavailable, match="503"):
                client.get("osrm", OSRM_URL)

        route.respond(200, json=OK)
        assert client.get("osrm", OSRM_URL).json() == OK


class TestBulkhead:
    def test_a_full_provider_times_out_waiting_for_a_slot(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = api.get(OSRM_URL).respond(200, json=OK)
        client = make_client(clock)
        slots = client._providers["osrm"].slots  # noqa: SLF001 - simulate a busy provider
        assert slots.acquire(blocking=False)

        with pytest.raises(UpstreamTimeout, match="slot"):
            client.get("osrm", OSRM_URL, deadline=Deadline(0.02, clock))

        assert not route.called
        slots.release()
        assert client.get("osrm", OSRM_URL).json() == OK

    def test_time_spent_waiting_for_a_slot_comes_out_of_the_request_timeout(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = api.get(OSRM_URL).respond(200, json=OK)
        client = make_client(clock)

        class SlowSlots:
            """Acquiring takes three seconds of the budget."""

            def acquire(self, timeout: float) -> bool:  # noqa: ARG002
                clock.advance(3.0)
                return True

            def release(self) -> None:
                pass

        client._providers["osrm"].slots = SlowSlots()  # type: ignore[assignment]  # noqa: SLF001

        client.get("osrm", OSRM_URL, deadline=Deadline(5.0, clock))

        assert route.calls.last.request.extensions["timeout"]["read"] == pytest.approx(2.0)

    def test_a_budget_used_up_waiting_for_a_slot_stops_the_call(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = api.get(OSRM_URL).respond(200, json=OK)
        client = make_client(clock)

        class SlowSlots:
            def acquire(self, timeout: float) -> bool:  # noqa: ARG002
                clock.advance(10.0)
                return True

            def release(self) -> None:
                pass

        client._providers["osrm"].slots = SlowSlots()  # type: ignore[assignment]  # noqa: SLF001

        with pytest.raises(UpstreamTimeout, match="deadline"):
            client.get("osrm", OSRM_URL, deadline=Deadline(5.0, clock))

        assert not route.called

    def test_waiting_for_a_slot_is_not_held_against_the_provider(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        api.get(OSRM_URL).respond(200, json=OK)
        client = make_client(clock)
        slots = client._providers["osrm"].slots  # noqa: SLF001
        assert slots.acquire(blocking=False)
        for _ in range(4):
            with pytest.raises(UpstreamTimeout):
                client.get("osrm", OSRM_URL, deadline=Deadline(0.01, clock))
        slots.release()

        assert client.get("osrm", OSRM_URL).json() == OK

    def test_the_slot_is_released_after_a_failure(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        client = make_client(clock)
        api.get(OSRM_URL).mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(UpstreamTimeout):
            client.get("osrm", OSRM_URL)
        api.get(OSRM_URL).respond(200, json=OK)

        assert client.get("osrm", OSRM_URL).json() == OK


class TestHostAllowlist:
    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.example/route",
            "https://evil.router.project-osrm.org/route",
            "https://router.project-osrm.org.evil.example/route",
            "https://router.project-osrm.org@evil.example/route",
            "http://router.project-osrm.org/route",
            "ftp://router.project-osrm.org/route",
            "https://[not-a-host/route",
            "https://router.project-osrm.org:notaport/route",
            "/relative/path",
        ],
        ids=[
            "other-host",
            "prefix-subdomain",
            "suffix-trick",
            "userinfo-trick",
            "plain-http",
            "other-scheme",
            "invalid-url",
            "invalid-port",
            "relative",
        ],
    )
    def test_rejects_urls_outside_the_allowlist_before_any_request(
        self, api: respx.MockRouter, clock: FakeClock, url: str
    ) -> None:
        catch_all = api.route().respond(200, json=OK)

        with pytest.raises(HostNotAllowed):
            make_client(clock).get("osrm", url)

        assert not catch_all.called

    def test_host_matching_ignores_case_and_port(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        api.get("https://router.project-osrm.org:8443/route").respond(200, json=OK)

        response = make_client(clock).get("osrm", "HTTPS://Router.Project-OSRM.org:8443/route")

        assert response.json() == OK

    def test_allowlist_entries_from_configuration_are_matched_case_insensitively(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        api.get(OSRM_URL).respond(200, json=OK)
        client = UpstreamClient(
            [ProviderPolicy("osrm", timeout_s=8.0, max_concurrency=1)],
            ["Router.Project-OSRM.org"],
            USER_AGENT,
            clock=clock,
            sleep=clock.sleep,
        )

        assert client.get("osrm", OSRM_URL).json() == OK

    def test_a_rejected_url_does_not_count_against_the_provider(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        client = make_client(clock)
        api.get(OSRM_URL).respond(200, json=OK)
        for _ in range(5):
            with pytest.raises(HostNotAllowed):
                client.get("osrm", "https://evil.example/")

        assert client.get("osrm", OSRM_URL).json() == OK


class TestLifecycle:
    def test_close_releases_the_connection_pool(self, clock: FakeClock) -> None:
        http = httpx.Client()
        client = make_client(clock, http_client=http)

        client.close()

        assert http.is_closed


class TestDefaultPolicies:
    def test_follow_the_resilience_table(self) -> None:
        policies = {policy.name: policy for policy in default_policies()}

        assert policies["osrm"].timeout_s == 8.0
        assert policies["osrm"].max_concurrency == 1
        assert policies["open-meteo"].timeout_s == 10.0
        assert policies["open-meteo"].max_concurrency == 4
        assert policies["photon"].timeout_s == 4.0
        assert policies["photon"].max_concurrency == 2
        assert policies["nominatim"].timeout_s == 4.0
        assert {p.connect_timeout_s for p in policies.values()} == {3.0}
        assert {p.retries for p in policies.values()} == {1}
        assert {p.failure_threshold for p in policies.values()} == {3}
        assert {p.reset_after_s for p in policies.values()} == {60.0}
        assert {p.backoff_base_s for p in policies.values()} == {0.3}


class TestRejectedRequests:
    def test_a_rejected_request_exposes_the_status_and_a_short_body(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        api.get(OSRM_URL).respond(400, json={"code": "NoRoute", "message": "Impossible route"})

        with pytest.raises(UpstreamError) as raised:
            make_client(clock).get("osrm", OSRM_URL)

        assert raised.value.status == 400
        assert raised.value.body is not None
        assert "NoRoute" in raised.value.body
        assert "NoRoute" not in str(raised.value)

    def test_a_huge_error_body_is_cut_short(self, api: respx.MockRouter, clock: FakeClock) -> None:
        api.get(OSRM_URL).respond(400, text="x" * 50_000)

        with pytest.raises(UpstreamError) as raised:
            make_client(clock).get("osrm", OSRM_URL)

        assert raised.value.body is not None
        assert len(raised.value.body) == 2_000


class TestGates:
    def gated_client(self, clock: FakeClock) -> UpstreamClient:
        spacing = MinSpacing(1.1, "osrm", clock, clock.sleep)
        return UpstreamClient(
            [
                ProviderPolicy("osrm", timeout_s=8.0, max_concurrency=1),
                ProviderPolicy("open-meteo", timeout_s=10.0, max_concurrency=4),
            ],
            ALLOWED,
            USER_AGENT,
            clock=clock,
            sleep=clock.sleep,
            jitter=FixedJitter(1.0),
            gates={"osrm": spacing},
        )

    def test_requests_to_a_gated_provider_are_spaced(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        api.get(OSRM_URL).respond(200, json=OK)
        client = self.gated_client(clock)

        client.get("osrm", OSRM_URL)
        client.get("osrm", OSRM_URL)

        assert clock.sleeps == [pytest.approx(1.1)]

    def test_a_retry_is_spaced_from_the_failed_attempt_too(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        api.get(OSRM_URL).mock(side_effect=[httpx.Response(503), httpx.Response(200, json=OK)])

        self.gated_client(clock).get("osrm", OSRM_URL)

        assert clock.sleeps == [pytest.approx(0.3), pytest.approx(0.8)]  # backoff, then the rest

    def test_other_providers_are_not_gated(self, api: respx.MockRouter, clock: FakeClock) -> None:
        api.get(WEATHER_URL).respond(200, json={})
        client = self.gated_client(clock)

        client.get("open-meteo", WEATHER_URL)
        client.get("open-meteo", WEATHER_URL)

        assert clock.sleeps == []

    def test_a_deadline_too_short_for_the_spacing_stops_the_call(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        route = api.get(OSRM_URL).respond(200, json=OK)
        client = self.gated_client(clock)
        client.get("osrm", OSRM_URL)

        with pytest.raises(UpstreamTimeout, match="spacing"):
            client.get("osrm", OSRM_URL, deadline=Deadline(0.5, clock))

        assert route.call_count == 1

    def test_waiting_for_the_spacing_is_not_held_against_the_provider(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        api.get(OSRM_URL).respond(200, json=OK)
        client = self.gated_client(clock)
        client.get("osrm", OSRM_URL)
        for _ in range(4):
            with pytest.raises(UpstreamTimeout):
                client.get("osrm", OSRM_URL, deadline=Deadline(0.5, clock))

        clock.advance(2.0)
        assert client.get("osrm", OSRM_URL).json() == OK

    def test_the_settings_client_spaces_osrm_requests_process_wide(
        self, api: respx.MockRouter, settings: Any
    ) -> None:
        settings.UPSTREAM_ALLOWED_HOSTS = ["router.project-osrm.org"]
        api.get(OSRM_URL).respond(200, json=OK)

        first, second = upstream_client_from_settings(), upstream_client_from_settings()
        gate = first._gates["osrm"]  # noqa: SLF001
        assert gate is second._gates["osrm"]  # noqa: SLF001
        assert isinstance(gate, MinSpacing)
        assert gate.spacing_s == 1.1


class TestFromSettings:
    def test_uses_the_configured_user_agent_and_allowlist(
        self, api: respx.MockRouter, settings: Any
    ) -> None:
        settings.UPSTREAM_USER_AGENT = "ConfiguredAgent/9"
        settings.UPSTREAM_ALLOWED_HOSTS = ["router.project-osrm.org"]
        route = api.get(OSRM_URL).respond(200, json=OK)
        client = upstream_client_from_settings()

        client.get("osrm", OSRM_URL)

        assert route.calls.last.request.headers["User-Agent"] == "ConfiguredAgent/9"
        with pytest.raises(HostNotAllowed):
            client.get("open-meteo", WEATHER_URL)

    def test_the_default_allowlist_covers_every_provider_and_nothing_else(
        self, settings: Any
    ) -> None:
        assert sorted(settings.UPSTREAM_ALLOWED_HOSTS) == [
            "api.open-meteo.com",
            "api.openrouteservice.org",
            "nominatim.openstreetmap.org",
            "photon.komoot.io",
            "router.project-osrm.org",
        ]
        assert "github.com/syntrydy/truck-routing" in settings.UPSTREAM_USER_AGENT
