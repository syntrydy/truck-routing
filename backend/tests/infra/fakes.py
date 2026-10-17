"""Deterministic stand-ins for time and randomness."""


class FakeClock:
    """A monotonic clock that only moves when told to; ``sleep`` advances it and records."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FixedJitter:
    """Stands in for ``random.Random``: ``uniform(a, b)`` returns ``a + fraction * (b - a)``."""

    def __init__(self, fraction: float = 1.0) -> None:
        self.fraction = fraction
        self.calls: list[tuple[float, float]] = []

    def uniform(self, low: float, high: float) -> float:
        self.calls.append((low, high))
        return low + self.fraction * (high - low)
