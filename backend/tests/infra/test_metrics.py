import threading
from contextvars import copy_context

import pytest

from planner.infra.metrics import (
    UpstreamUsage,
    metrics_scope,
    record_cache_lookup,
    record_upstream_call,
    record_weather_batch_lost,
    record_weather_points,
)


class TestRecording:
    def test_nothing_happens_outside_a_scope(self) -> None:
        record_upstream_call("osrm", 1.0)
        record_cache_lookup(hit=True)
        record_weather_points(3)

        with metrics_scope() as metrics:
            pass

        assert metrics.upstream == {}
        assert metrics.cache_hit_ratio is None
        assert metrics.weather_points == 0

    def test_calls_are_counted_and_timed_per_provider(self) -> None:
        with metrics_scope() as metrics:
            record_upstream_call("osrm", 0.5)
            record_upstream_call("open-meteo", 1.0)
            record_upstream_call("open-meteo", 0.25)

        assert metrics.upstream == {
            "open-meteo": UpstreamUsage(2, 1.25),
            "osrm": UpstreamUsage(1, 0.5),
        }

    def test_the_hit_ratio_is_hits_over_lookups(self) -> None:
        with metrics_scope() as metrics:
            for hit in (True, False, False, True, True):
                record_cache_lookup(hit=hit)

        assert (metrics.cache_hits, metrics.cache_misses) == (3, 2)
        assert metrics.cache_hit_ratio == pytest.approx(0.6)

    def test_weather_points_are_noted(self) -> None:
        with metrics_scope() as metrics:
            record_weather_points(42)

        assert metrics.weather_points == 42

    def test_lost_weather_batches_are_counted(self) -> None:
        record_weather_batch_lost()  # outside a scope: nothing happens
        with metrics_scope() as metrics:
            record_weather_batch_lost()
            record_weather_batch_lost()

        assert metrics.weather_batches_lost == 2

    def test_scopes_are_separate_and_nest(self) -> None:
        with metrics_scope() as outer:
            record_cache_lookup(hit=True)
            with metrics_scope() as inner:
                record_cache_lookup(hit=False)
            record_cache_lookup(hit=True)

        assert (outer.cache_hits, outer.cache_misses) == (2, 0)
        assert (inner.cache_hits, inner.cache_misses) == (0, 1)

    def test_a_scope_ends_with_its_block_even_on_error(self) -> None:
        with pytest.raises(RuntimeError), metrics_scope():
            raise RuntimeError

        record_cache_lookup(hit=True)  # no scope left to count it

    def test_threads_started_in_a_copy_of_the_context_record_into_the_scope(self) -> None:
        def work() -> None:
            for _ in range(200):
                record_upstream_call("p", 0.1)

        with metrics_scope() as metrics:
            threads = [threading.Thread(target=copy_context().run, args=(work,)) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        assert metrics.upstream["p"].calls == 1600
