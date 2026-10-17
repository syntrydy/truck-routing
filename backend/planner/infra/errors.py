"""Typed failures of calls to upstream providers.

The API layer maps these once to HTTP responses (SPEC section 5); providers and the
service raise and catch them but never build responses themselves.
"""


class UpstreamError(Exception):
    """A provider answered with an error that retrying would not fix (HTTP 502).

    ``status`` and ``body`` (shortened) are set when the provider rejected the request, so
    an adapter can read the reason; the body is kept out of the message and the logs.
    """

    def __init__(
        self, provider: str, message: str, *, status: int | None = None, body: str | None = None
    ) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.message = message
        self.status = status
        self.body = body


class UpstreamTimeout(UpstreamError):  # noqa: N818 - named for the HTTP condition it maps to
    """The provider did not answer in time, or the request deadline ran out (HTTP 504)."""


class UpstreamWaitTimeout(UpstreamTimeout):  # noqa: N818
    """Timed out before the provider was asked (no budget, no free slot, rate-limit spacing).

    The provider is not at fault, so this never counts against its circuit breaker.
    """


class UpstreamUnavailable(UpstreamError):  # noqa: N818
    """The provider is not serving: circuit open, connection failures, 5xx or 429 (HTTP 503).

    Fallback chains (for example OSRM to openrouteservice) switch provider on this error.
    """


class UpstreamContractError(UpstreamError):
    """The provider answered, but not in the shape or units we rely on (HTTP 502)."""


class HostNotAllowed(ValueError):  # noqa: N818
    """An outbound request targeted a host outside the allowlist, or used a bad scheme."""
