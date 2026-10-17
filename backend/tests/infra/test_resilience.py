import threading

import pytest

from planner.infra.resilience import (
    BreakerState,
    CircuitBreaker,
    Deadline,
    current_deadline,
    deadline_scope,
)
from tests.infra.fakes import FakeClock


class TestDeadline:
    def test_remaining_counts_down_with_the_clock(self) -> None:
        clock = FakeClock()
        deadline = Deadline(20.0, clock)

        clock.advance(5.0)

        assert deadline.remaining() == pytest.approx(15.0)
        assert not deadline.expired

    def test_remaining_never_goes_negative(self) -> None:
        clock = FakeClock()
        deadline = Deadline(1.0, clock)

        clock.advance(10.0)

        assert deadline.remaining() == 0.0
        assert deadline.expired


class TestDeadlineScope:
    def test_no_deadline_outside_a_scope(self) -> None:
        assert current_deadline() is None

    def test_scope_makes_a_deadline_current_and_restores_afterwards(self) -> None:
        with deadline_scope(20.0, FakeClock()) as deadline:
            assert current_deadline() is deadline

        assert current_deadline() is None

    def test_scopes_nest(self) -> None:
        with deadline_scope(20.0, FakeClock()) as outer:
            with deadline_scope(5.0, FakeClock()) as inner:
                assert current_deadline() is inner
            assert current_deadline() is outer

    def test_scope_is_restored_after_an_error(self) -> None:
        with pytest.raises(RuntimeError), deadline_scope(20.0, FakeClock()):
            raise RuntimeError

        assert current_deadline() is None

    def test_other_threads_do_not_see_the_scope(self) -> None:
        seen: list[object] = []

        with deadline_scope(20.0, FakeClock()):
            thread = threading.Thread(target=lambda: seen.append(current_deadline()))
            thread.start()
            thread.join()

        assert seen == [None]


class TestCircuitBreaker:
    def make(self) -> tuple[CircuitBreaker, FakeClock]:
        clock = FakeClock()
        return CircuitBreaker(failure_threshold=3, reset_after_s=60.0, clock=clock), clock

    def test_starts_closed_and_allows_calls(self) -> None:
        breaker, _ = self.make()

        assert breaker.state is BreakerState.CLOSED
        assert breaker.allow()

    def test_opens_after_three_consecutive_failures(self) -> None:
        breaker, _ = self.make()

        for _ in range(2):
            breaker.record_failure()
            assert breaker.state is BreakerState.CLOSED
        breaker.record_failure()

        assert breaker.state is BreakerState.OPEN
        assert not breaker.allow()

    def test_a_success_resets_the_failure_count(self) -> None:
        breaker, _ = self.make()

        breaker.record_failure()
        breaker.record_failure()
        breaker.record_success()
        breaker.record_failure()
        breaker.record_failure()

        assert breaker.state is BreakerState.CLOSED

    def test_stays_open_until_the_reset_time_has_passed(self) -> None:
        breaker, clock = self.make()
        for _ in range(3):
            breaker.record_failure()

        clock.advance(59.9)
        assert not breaker.allow()

        clock.advance(0.2)
        assert breaker.state is BreakerState.HALF_OPEN

    def test_half_open_lets_a_single_probe_through(self) -> None:
        breaker, clock = self.make()
        for _ in range(3):
            breaker.record_failure()
        clock.advance(60.0)

        assert breaker.allow()
        assert not breaker.allow()

    def test_a_successful_probe_closes_the_breaker(self) -> None:
        breaker, clock = self.make()
        for _ in range(3):
            breaker.record_failure()
        clock.advance(60.0)
        breaker.allow()

        breaker.record_success()

        assert breaker.state is BreakerState.CLOSED
        assert breaker.allow()
        assert breaker.allow()

    def test_a_failed_probe_reopens_the_breaker_for_a_full_period(self) -> None:
        breaker, clock = self.make()
        for _ in range(3):
            breaker.record_failure()
        clock.advance(60.0)
        breaker.allow()

        breaker.record_failure()

        assert breaker.state is BreakerState.OPEN
        clock.advance(59.0)
        assert not breaker.allow()
        clock.advance(1.0)
        assert breaker.allow()

    def test_a_released_probe_lets_the_next_caller_probe(self) -> None:
        breaker, clock = self.make()
        for _ in range(3):
            breaker.record_failure()
        clock.advance(60.0)
        assert breaker.allow()

        breaker.release()

        assert breaker.state is BreakerState.HALF_OPEN
        assert breaker.allow()

    def test_releasing_a_closed_breaker_changes_nothing(self) -> None:
        breaker, _ = self.make()

        breaker.release()

        assert breaker.state is BreakerState.CLOSED
        assert breaker.allow()

    def test_failure_count_is_per_breaker(self) -> None:
        first, _ = self.make()
        second, _ = self.make()

        for _ in range(3):
            first.record_failure()

        assert first.state is BreakerState.OPEN
        assert second.state is BreakerState.CLOSED
