"""Cache-aside with stale-if-error, and the cache keys (SPEC sections 4.1, 4.4, 6).

Entries remember when they were fetched. A fresh entry is returned as is; an older one is
refreshed through the loader, and if that fails because the upstream is down, the old value
is served (flagged stale) for as long as it is younger than the stale limit. The cache is
disposable: if the backend itself fails, calls simply behave as if it were empty.
"""

import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.core.cache.backends.base import BaseCache

from planner.domain.models import LatLon
from planner.infra.errors import UpstreamError

logger = logging.getLogger(__name__)

KEY_PREFIX = "truck:v1"
ROUTE_DECIMALS = 3
WEATHER_DECIMALS = 1
GEOCODE_KEY_LENGTH = 32


@dataclass(frozen=True, slots=True)
class CacheResult[T]:
    """A value and whether it is older than its fresh lifetime (served after a failure)."""

    value: T
    stale: bool = False


class StaleIfErrorCache:
    """Cache-aside helper over a Django cache backend."""

    def __init__(self, backend: BaseCache, clock: Callable[[], float] = time.time) -> None:
        self._backend = backend
        self._clock = clock

    def get_or_load[T](  # noqa: PLR0913 - the lifetimes and failure types are all needed
        self,
        key: str,
        loader: Callable[[], T],
        *,
        fresh_ttl_s: float,
        max_stale_age_s: float,
        catch: tuple[type[Exception], ...] = (UpstreamError,),
    ) -> CacheResult[T]:
        """Return the cached value, refreshing it through ``loader`` once it is not fresh.

        If ``loader`` raises one of ``catch`` and the cached value is younger than
        ``max_stale_age_s``, that value is returned with ``stale=True``; otherwise the
        error propagates.
        """
        entry = self._read(key)
        if entry is not None and self._age(entry) < fresh_ttl_s:
            return CacheResult(entry["value"])
        try:
            value = loader()
        except catch:
            if entry is not None and self._age(entry) < max_stale_age_s:
                logger.warning("serving stale cache entry after upstream failure")
                return CacheResult(entry["value"], stale=True)
            raise
        self._write(key, value, timeout_s=max_stale_age_s)
        return CacheResult(value)

    def _age(self, entry: dict[str, Any]) -> float:
        return self._clock() - float(entry["fetched_at"])

    def _read(self, key: str) -> dict[str, Any] | None:
        try:
            entry = self._backend.get(key)
        except Exception:
            logger.warning("cache read failed; treating as a miss", exc_info=True)
            return None
        if isinstance(entry, dict) and "value" in entry and "fetched_at" in entry:
            return entry
        return None

    def _write(self, key: str, value: object, *, timeout_s: float) -> None:
        try:
            self._backend.set(
                key,
                {"value": value, "fetched_at": self._clock()},
                timeout=max(1, round(timeout_s)),
            )
        except Exception:
            logger.warning("cache write failed; continuing without caching", exc_info=True)


def route_key(origin: LatLon, destination: LatLon, provider: str) -> str:
    """Key of a route between two points, which are rounded to about 100 m."""
    return (
        f"{KEY_PREFIX}:route:{provider}:"
        f"{_coordinate(origin, ROUTE_DECIMALS)}:{_coordinate(destination, ROUTE_DECIMALS)}"
    )


def weather_key(point: LatLon) -> str:
    """Key of a point's hourly weather; points are rounded to 0.1 degrees."""
    return f"{KEY_PREFIX}:weather:{_coordinate(point, WEATHER_DECIMALS)}"


def geocode_key(query: str, provider: str) -> str:
    """Key of a geocoding query, ignoring case and extra whitespace."""
    normalised = " ".join(query.lower().split())
    digest = hashlib.sha256(normalised.encode()).hexdigest()[:GEOCODE_KEY_LENGTH]
    return f"{KEY_PREFIX}:geocode:{provider}:{digest}"


def _coordinate(point: LatLon, decimals: int) -> str:
    return f"{_round(point.lat, decimals)},{_round(point.lon, decimals)}"


def _round(value: float, decimals: int) -> str:
    text = f"{round(value, decimals):.{decimals}f}"
    return text[1:] if text.startswith("-") and float(text) == 0 else text  # no "-0.0"
