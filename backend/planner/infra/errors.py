"""Typed failures of calls to upstream providers.

The API layer maps these once to HTTP responses (SPEC section 5); providers and the
service raise and catch them but never build responses themselves.
"""


class UpstreamError(Exception):
    """A provider answered with an error that retrying would not fix (HTTP 502)."""

    def __init__(self, provider: str, message: str) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.message = message


class UpstreamTimeout(UpstreamError):  # noqa: N818 - named for the HTTP condition it maps to
    """The provider did not answer in time, or the request deadline ran out (HTTP 504)."""


class UpstreamUnavailable(UpstreamError):  # noqa: N818
    """The provider is not serving: circuit open, connection failures, 5xx or 429 (HTTP 503).

    Fallback chains (for example OSRM to openrouteservice) switch provider on this error.
    """


class UpstreamContractError(UpstreamError):
    """The provider answered, but not in the shape or units we rely on (HTTP 502)."""


class HostNotAllowed(ValueError):  # noqa: N818
    """An outbound request targeted a host outside the allowlist, or used a bad scheme."""
