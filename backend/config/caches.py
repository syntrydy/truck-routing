"""Django ``CACHES`` setting: in-process memory by default, Redis when a URL is given."""

from typing import Any

REDIS_SOCKET_TIMEOUT_S = 1
# Hourly weather for a few hundred grid points per plan, about 10 KB each when pickled.
LOCMEM_MAX_ENTRIES = 2_000


def caches_for(redis_url: str) -> dict[str, dict[str, Any]]:
    """The cache configuration for an optional ``REDIS_URL``.

    The cache only holds disposable data, so the Redis timeouts are short: an outage must
    cost a request about a second, not its whole budget.
    """
    if not redis_url:
        return {
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "OPTIONS": {"MAX_ENTRIES": LOCMEM_MAX_ENTRIES},
            }
        }
    return {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": redis_url,
            "OPTIONS": {
                "socket_connect_timeout": REDIS_SOCKET_TIMEOUT_S,
                "socket_timeout": REDIS_SOCKET_TIMEOUT_S,
            },
        }
    }
