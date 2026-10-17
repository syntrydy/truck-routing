"""Deadline budget and circuit breaker, with injectable time for deterministic tests."""

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from enum import StrEnum

Clock = Callable[[], float]


class Deadline:
    """A time budget shared by all calls made for one request."""

    def __init__(self, budget_s: float, clock: Clock = time.monotonic) -> None:
        self._clock = clock
        self._expires_at = clock() + budget_s

    def remaining(self) -> float:
        """Seconds left, never negative."""
        return max(0.0, self._expires_at - self._clock())

    @property
    def expired(self) -> bool:
        return self.remaining() <= 0.0


_current: ContextVar[Deadline | None] = ContextVar("current_deadline", default=None)


def current_deadline() -> Deadline | None:
    """The deadline of the enclosing ``deadline_scope``, if any."""
    return _current.get()


@contextmanager
def deadline_scope(budget_s: float, clock: Clock = time.monotonic) -> Iterator[Deadline]:
    """Make a ``Deadline`` of ``budget_s`` seconds current for the enclosed block."""
    deadline = Deadline(budget_s, clock)
    token = _current.set(deadline)
    try:
        yield deadline
    finally:
        _current.reset(token)


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Stops calling a failing provider, then lets one probe through to test it.

    Opens after ``failure_threshold`` consecutive failures. After ``reset_after_s`` it
    becomes half-open: a single call is allowed; success closes the breaker, failure opens
    it again. Every ``allow()`` that returns True must be followed by exactly one of
    ``record_success``, ``record_failure`` or ``release``.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        reset_after_s: float = 60.0,
        clock: Clock = time.monotonic,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._reset_after_s = reset_after_s
        self._clock = clock
        self._lock = threading.Lock()
        self._failures = 0
        self._opened_at = 0.0
        self._state = BreakerState.CLOSED
        self._probe_in_flight = False

    @property
    def state(self) -> BreakerState:
        with self._lock:
            return self._effective_state()

    def allow(self) -> bool:
        """Whether a call may go ahead now."""
        with self._lock:
            state = self._effective_state()
            if state is BreakerState.CLOSED:
                return True
            if state is BreakerState.HALF_OPEN and not self._probe_in_flight:
                self._state = BreakerState.HALF_OPEN
                self._probe_in_flight = True
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._state = BreakerState.CLOSED
            self._probe_in_flight = False

    def record_failure(self) -> None:
        with self._lock:
            self._probe_in_flight = False
            if self._state is BreakerState.HALF_OPEN:
                self._open()
                return
            self._failures += 1
            if self._failures >= self._failure_threshold:
                self._open()

    def release(self) -> None:
        """Give back a permit without recording an outcome (the call never happened)."""
        with self._lock:
            self._probe_in_flight = False

    def _open(self) -> None:
        self._state = BreakerState.OPEN
        self._opened_at = self._clock()

    def _effective_state(self) -> BreakerState:
        if (
            self._state is BreakerState.OPEN
            and self._clock() - self._opened_at >= self._reset_after_s
        ):
            return BreakerState.HALF_OPEN
        return self._state
