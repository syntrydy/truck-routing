"""Resilient HTTP access to upstream providers (SPEC sections 6 and 8).

Every outbound call goes through ``UpstreamClient``: only allowlisted https hosts, a
User-Agent, per-provider timeouts capped by the request deadline, one jittered retry on
transient failures, a circuit breaker and a concurrency limit per provider.
"""

import logging
import random
import threading
import time
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from django.conf import settings

from planner.infra.errors import (
    HostNotAllowed,
    UpstreamContractError,
    UpstreamError,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from planner.infra.resilience import CircuitBreaker, Clock, Deadline, current_deadline

logger = logging.getLogger(__name__)

HTTP_TOO_MANY_REQUESTS = 429
HTTP_SERVER_ERROR = 500
HTTP_CLIENT_ERROR = 400
HTTPS = "https"


class Jitter(Protocol):
    """The part of ``random.Random`` used for backoff."""

    def uniform(self, a: float, b: float, /) -> float: ...


@dataclass(frozen=True, slots=True)
class ProviderPolicy:
    """Resilience settings of one provider."""

    name: str
    timeout_s: float
    max_concurrency: int
    connect_timeout_s: float = 3.0
    failure_threshold: int = 3
    reset_after_s: float = 60.0
    retries: int = 1
    backoff_base_s: float = 0.3


ROUTING_TIMEOUT_S = 8.0
WEATHER_TIMEOUT_S = 10.0
GEOCODE_TIMEOUT_S = 4.0


def default_policies() -> list[ProviderPolicy]:
    """The provider policies of SPEC section 6."""
    return [
        ProviderPolicy("osrm", ROUTING_TIMEOUT_S, max_concurrency=1),
        ProviderPolicy("openrouteservice", ROUTING_TIMEOUT_S, max_concurrency=1),
        ProviderPolicy("open-meteo", WEATHER_TIMEOUT_S, max_concurrency=4),
        ProviderPolicy("photon", GEOCODE_TIMEOUT_S, max_concurrency=2),
        ProviderPolicy("nominatim", GEOCODE_TIMEOUT_S, max_concurrency=2),
    ]


class _LocalTimeout(UpstreamTimeout):
    """Timed out before the provider was asked (no budget or no free slot): not its fault."""


class _ProviderState:
    def __init__(self, policy: ProviderPolicy, clock: Clock) -> None:
        self.policy = policy
        self.breaker = CircuitBreaker(policy.failure_threshold, policy.reset_after_s, clock)
        self.slots = threading.BoundedSemaphore(policy.max_concurrency)


class UpstreamClient:
    """Synchronous, thread-safe client for the configured upstream providers."""

    def __init__(  # noqa: PLR0913 - collaborators are injected for testability
        self,
        policies: Iterable[ProviderPolicy],
        allowed_hosts: Collection[str],
        user_agent: str,
        *,
        http_client: httpx.Client | None = None,
        clock: Clock = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Jitter | None = None,
    ) -> None:
        self._providers: Mapping[str, _ProviderState] = {
            policy.name: _ProviderState(policy, clock) for policy in policies
        }
        self._allowed_hosts = frozenset(host.lower() for host in allowed_hosts)
        self._user_agent = user_agent
        self._http = http_client or httpx.Client(follow_redirects=False)
        self._sleep = sleep
        self._jitter: Jitter = jitter or random.Random()  # noqa: S311  # nosec B311 - backoff jitter, not security

    def close(self) -> None:
        """Release the connection pool."""
        self._http.close()

    def get_json(
        self,
        provider: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        deadline: Deadline | None = None,
    ) -> Any:  # noqa: ANN401 - decoded JSON has no useful static type
        """GET ``url`` and decode the JSON body."""
        response = self.get(provider, url, params=params, deadline=deadline)
        try:
            return response.json()
        except ValueError as error:
            msg = "response is not valid JSON"
            raise UpstreamContractError(provider, msg) from error

    def get(
        self,
        provider: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        deadline: Deadline | None = None,
    ) -> httpx.Response:
        """GET ``url`` from ``provider`` and return a successful response.

        Raises ``HostNotAllowed`` for a disallowed URL, ``UpstreamUnavailable`` when the
        breaker is open or the provider keeps failing, ``UpstreamTimeout`` when time runs
        out, and ``UpstreamError`` when the provider rejects the request.
        """
        state = self._providers.get(provider)
        if state is None:
            msg = f"unknown provider {provider!r}"
            raise ValueError(msg)
        self._check_url(url)
        deadline = deadline or current_deadline()

        if not state.breaker.allow():
            msg = "circuit open"
            raise UpstreamUnavailable(provider, msg)
        try:
            response = self._send_with_retries(state, url, params, deadline)
        except _LocalTimeout:
            state.breaker.release()
            raise
        except (UpstreamTimeout, UpstreamUnavailable):
            state.breaker.record_failure()
            raise
        except UpstreamError:
            state.breaker.record_success()  # the provider is healthy; it rejected our request
            raise
        state.breaker.record_success()
        return response

    def _check_url(self, url: str) -> None:
        try:
            parsed = httpx.URL(url)
        except httpx.InvalidURL as error:
            msg = "invalid URL"
            raise HostNotAllowed(msg) from error
        if parsed.scheme != HTTPS:
            msg = f"scheme {parsed.scheme!r} is not allowed"
            raise HostNotAllowed(msg)
        if parsed.host not in self._allowed_hosts:  # httpx has lowercased the host
            msg = f"host {parsed.host!r} is not allowed"
            raise HostNotAllowed(msg)

    def _send_with_retries(
        self,
        state: _ProviderState,
        url: str,
        params: Mapping[str, Any] | None,
        deadline: Deadline | None,
    ) -> httpx.Response:
        policy = state.policy
        last_failure: UpstreamUnavailable | None = None
        for attempt in range(policy.retries + 1):
            if attempt > 0:
                delay = self._jitter.uniform(0.0, policy.backoff_base_s * 2 ** (attempt - 1))
                if deadline is not None and delay >= deadline.remaining():
                    break
                self._sleep(delay)
            try:
                response, failure = self._attempt(state, url, params, deadline)
            except _LocalTimeout:
                if last_failure is None:
                    raise
                break  # no time left to retry: report the failure that made us retry
            if response is not None:
                return response
            last_failure = failure
            logger.info("retryable failure from %s (attempt %d)", policy.name, attempt + 1)
        if last_failure is None:  # pragma: no cover - the loop always records a failure first
            msg = "no attempt was made"
            raise UpstreamUnavailable(policy.name, msg)
        raise last_failure

    def _attempt(
        self,
        state: _ProviderState,
        url: str,
        params: Mapping[str, Any] | None,
        deadline: Deadline | None,
    ) -> tuple[httpx.Response | None, UpstreamUnavailable | None]:
        """One request. Returns the response, or the retryable failure."""
        policy = state.policy
        wait_s = _call_timeout(policy, deadline)
        if wait_s is None:
            msg = "request deadline exhausted"
            raise _LocalTimeout(policy.name, msg)
        if not state.slots.acquire(timeout=wait_s):
            msg = "no free connection slot in time"
            raise _LocalTimeout(policy.name, msg)
        try:
            # Waiting for the slot used up budget, so the timeout is worked out again.
            timeout_s = _call_timeout(policy, deadline)
            if timeout_s is None:
                msg = "request deadline exhausted"
                raise _LocalTimeout(policy.name, msg)
            response = self._http.get(
                url,
                params=params,
                headers={"User-Agent": self._user_agent},
                timeout=httpx.Timeout(timeout_s, connect=min(policy.connect_timeout_s, timeout_s)),
            )
        except (httpx.ConnectTimeout, httpx.ConnectError) as error:
            return None, UpstreamUnavailable(
                policy.name, f"cannot connect ({type(error).__name__})"
            )
        except httpx.TimeoutException as error:
            msg = f"timed out after {timeout_s:.1f} s"
            raise UpstreamTimeout(policy.name, msg) from error
        except httpx.TransportError as error:
            return None, UpstreamUnavailable(
                policy.name, f"connection failed ({type(error).__name__})"
            )
        finally:
            state.slots.release()

        status = response.status_code
        if status == HTTP_TOO_MANY_REQUESTS or status >= HTTP_SERVER_ERROR:
            return None, UpstreamUnavailable(policy.name, f"HTTP {status}")
        if status >= HTTP_CLIENT_ERROR or response.is_redirect:
            msg = f"HTTP {status}"
            raise UpstreamError(policy.name, msg)
        return response, None


def _call_timeout(policy: ProviderPolicy, deadline: Deadline | None) -> float | None:
    """The provider timeout capped by the time left, or ``None`` when none is left."""
    if deadline is None:
        return policy.timeout_s
    remaining = deadline.remaining()
    if remaining <= 0.0:
        return None
    return min(policy.timeout_s, remaining)


def upstream_client_from_settings() -> UpstreamClient:
    """Build the client from ``UPSTREAM_USER_AGENT`` and ``UPSTREAM_ALLOWED_HOSTS``."""
    return UpstreamClient(
        default_policies(),
        settings.UPSTREAM_ALLOWED_HOSTS,
        settings.UPSTREAM_USER_AGENT,
    )
