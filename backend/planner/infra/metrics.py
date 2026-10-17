"""What one request did, collected while it runs and reported once at the end (SPEC section 9).

The upstream client and the cache record into the current scope; outside a scope the
``record_*`` functions do nothing, so they are safe to call from anywhere.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class UpstreamUsage:
    """The calls made to one provider: how many, and the seconds they took in all."""

    calls: int
    seconds: float


@dataclass(slots=True)
class RequestMetrics:
    """Counters of one request. Safe to record into from several threads."""

    weather_points: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    _calls: dict[str, list[float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record_call(self, provider: str, seconds: float) -> None:
        with self._lock:
            self._calls.setdefault(provider, []).append(seconds)

    def record_lookup(self, *, hit: bool) -> None:
        with self._lock:
            if hit:
                self.cache_hits += 1
            else:
                self.cache_misses += 1

    @property
    def cache_hit_ratio(self) -> float | None:
        """Fresh answers over lookups; ``None`` when nothing was looked up."""
        lookups = self.cache_hits + self.cache_misses
        return self.cache_hits / lookups if lookups else None

    @property
    def upstream(self) -> dict[str, UpstreamUsage]:
        with self._lock:
            return {
                provider: UpstreamUsage(len(durations), sum(durations))
                for provider, durations in sorted(self._calls.items())
            }


_current: ContextVar[RequestMetrics | None] = ContextVar("current_metrics", default=None)


@contextmanager
def metrics_scope() -> Iterator[RequestMetrics]:
    """Collect the metrics of everything the enclosed block does."""
    metrics = RequestMetrics()
    token = _current.set(metrics)
    try:
        yield metrics
    finally:
        _current.reset(token)


def record_upstream_call(provider: str, seconds: float) -> None:
    """Note a call to ``provider`` that took ``seconds`` (all attempts and waits included)."""
    if (metrics := _current.get()) is not None:
        metrics.record_call(provider, seconds)


def record_cache_lookup(*, hit: bool) -> None:
    """Note a cache lookup that found a fresh value (``hit``) or had to load one."""
    if (metrics := _current.get()) is not None:
        metrics.record_lookup(hit=hit)


def record_weather_points(count: int) -> None:
    """Note how many distinct weather places the request needed."""
    if (metrics := _current.get()) is not None:
        metrics.weather_points = count
