"""Per-client rate limits (SPEC section 6), counted in the cache by ``django-ratelimit``.

The limit is only as good as the address it is keyed on. Behind a proxy every connection
comes from the proxy, and the caller can add anything to ``X-Forwarded-For`` before its
request reaches it, so the address is taken from the right of that header, where our own
proxies write, and never from the left, where the caller does.
"""

import ipaddress

from django.conf import settings
from django.http import HttpRequest

# The longest a refused client has to wait: limits are per minute. django-ratelimit does not
# report the time left in its window, so the whole period is the honest upper bound.
RETRY_AFTER_S = 60
# A placeholder bucket key for clients without an address, not a bind address.
UNKNOWN_ADDRESS = "0.0.0.0"  # noqa: S104  # nosec B104


def client_ip(request: HttpRequest) -> str:
    """The address to count ``request`` against.

    With ``TRUSTED_PROXY_COUNT`` = N, the address N entries from the right of
    ``X-Forwarded-For`` (the one our outermost trusted proxy recorded). If the header is too
    short or not an address, or no proxy is trusted, the connection's own address is used.
    """
    remote = str(request.META.get("REMOTE_ADDR", ""))
    trusted = int(settings.TRUSTED_PROXY_COUNT)
    if trusted > 0:
        header = str(request.META.get("HTTP_X_FORWARDED_FOR", ""))
        forwarded = [part.strip() for part in header.split(",")]
        if len(forwarded) >= trusted and _is_address(forwarded[-trusted]):
            return forwarded[-trusted]
    return remote if _is_address(remote) else UNKNOWN_ADDRESS


def plan_rate(group: str, request: HttpRequest) -> str:
    """The limit for plan requests, read at request time so that it can be changed."""
    return str(settings.PLAN_RATE_LIMIT)


def geocode_rate(group: str, request: HttpRequest) -> str:
    """The limit for geocode requests."""
    return str(settings.GEOCODE_RATE_LIMIT)


def _is_address(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True
