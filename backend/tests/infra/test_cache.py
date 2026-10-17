import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from django.core.cache.backends.locmem import LocMemCache

from planner.domain.models import HourlySeries, LatLon
from planner.infra.cache import (
    CacheResult,
    StaleIfErrorCache,
    geocode_key,
    route_key,
    weather_key,
)
from planner.infra.errors import UpstreamTimeout, UpstreamUnavailable
from tests.infra.fakes import FakeClock

FRESH_S = 1_800.0  # 30 minutes
MAX_STALE_S = 21_600.0  # 6 hours


@pytest.fixture
def backend() -> Iterator[LocMemCache]:
    cache = LocMemCache(f"test-{uuid.uuid4()}", {})
    yield cache
    cache.clear()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(start=1_000_000.0)


class Loader:
    """A loader that returns queued values or raises queued errors, and counts calls."""

    def __init__(self, *outcomes: object) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self) -> object:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def fetch(
    cache: StaleIfErrorCache, loader: Callable[[], object], key: str = "k"
) -> CacheResult[object]:
    return cache.get_or_load(key, loader, fresh_ttl_s=FRESH_S, max_stale_age_s=MAX_STALE_S)


class TestFreshness:
    def test_a_miss_loads_stores_and_returns_a_fresh_value(
        self, backend: LocMemCache, clock: FakeClock
    ) -> None:
        loader = Loader("value")

        result = fetch(StaleIfErrorCache(backend, clock), loader)

        assert result == CacheResult("value", stale=False)
        assert loader.calls == 1

    def test_a_fresh_entry_is_returned_without_loading(
        self, backend: LocMemCache, clock: FakeClock
    ) -> None:
        cache = StaleIfErrorCache(backend, clock)
        fetch(cache, Loader("first"))
        clock.advance(FRESH_S - 1)
        loader = Loader("second")

        result = fetch(cache, loader)

        assert result == CacheResult("first", stale=False)
        assert loader.calls == 0

    def test_an_entry_is_refreshed_once_its_fresh_lifetime_is_over(
        self, backend: LocMemCache, clock: FakeClock
    ) -> None:
        cache = StaleIfErrorCache(backend, clock)
        fetch(cache, Loader("first"))
        clock.advance(FRESH_S)

        result = fetch(cache, Loader("second"))

        assert result == CacheResult("second", stale=False)

    def test_a_refreshed_entry_is_fresh_again(self, backend: LocMemCache, clock: FakeClock) -> None:
        cache = StaleIfErrorCache(backend, clock)
        fetch(cache, Loader("first"))
        clock.advance(FRESH_S + 10)
        fetch(cache, Loader("second"))
        clock.advance(FRESH_S - 1)
        loader = Loader("third")

        assert fetch(cache, loader).value == "second"
        assert loader.calls == 0

    def test_keys_are_independent(self, backend: LocMemCache, clock: FakeClock) -> None:
        cache = StaleIfErrorCache(backend, clock)
        fetch(cache, Loader("a"), key="a")

        assert fetch(cache, Loader("b"), key="b").value == "b"
        assert fetch(cache, Loader(), key="a").value == "a"

    def test_domain_objects_survive_the_round_trip(
        self, backend: LocMemCache, clock: FakeClock
    ) -> None:
        series = HourlySeries(
            start=datetime(2026, 1, 15, 12, tzinfo=UTC),
            wind_mph=(1.0, None),
            gust_mph=(2.0, None),
            rain_in=(0.0, 0.1),
            showers_in=(0.0, 0.0),
            snowfall_in=(0.0, 0.0),
            weather_code=(0, None),
        )
        cache = StaleIfErrorCache(backend, clock)
        fetch(cache, Loader(series))

        assert fetch(cache, Loader()).value == series


class TestStaleIfError:
    def failing_after_expiry(
        self, backend: LocMemCache, clock: FakeClock, age_s: float, error: Exception
    ) -> CacheResult[object]:
        cache = StaleIfErrorCache(backend, clock)
        fetch(cache, Loader("old"))
        clock.advance(age_s)
        return fetch(cache, Loader(error))

    def test_serves_the_old_value_flagged_stale_when_the_upstream_is_down(
        self, backend: LocMemCache, clock: FakeClock
    ) -> None:
        result = self.failing_after_expiry(
            backend, clock, FRESH_S + 1, UpstreamUnavailable("p", "x")
        )

        assert result == CacheResult("old", stale=True)

    def test_timeouts_also_fall_back_to_the_stale_value(
        self, backend: LocMemCache, clock: FakeClock
    ) -> None:
        result = self.failing_after_expiry(backend, clock, FRESH_S + 1, UpstreamTimeout("p", "x"))

        assert result.stale is True

    def test_still_serves_just_inside_the_stale_limit(
        self, backend: LocMemCache, clock: FakeClock
    ) -> None:
        result = self.failing_after_expiry(
            backend, clock, MAX_STALE_S - 1, UpstreamUnavailable("p", "x")
        )

        assert result == CacheResult("old", stale=True)

    @pytest.mark.parametrize("age_s", [MAX_STALE_S, MAX_STALE_S + 1_000])
    def test_raises_the_upstream_error_once_the_stale_limit_has_passed(
        self, backend: LocMemCache, clock: FakeClock, age_s: float
    ) -> None:
        with pytest.raises(UpstreamUnavailable, match="down"):
            self.failing_after_expiry(backend, clock, age_s, UpstreamUnavailable("p", "down"))

    def test_raises_when_there_is_nothing_cached(
        self, backend: LocMemCache, clock: FakeClock
    ) -> None:
        with pytest.raises(UpstreamUnavailable):
            fetch(StaleIfErrorCache(backend, clock), Loader(UpstreamUnavailable("p", "down")))

    def test_other_errors_are_not_masked_by_a_stale_value(
        self, backend: LocMemCache, clock: FakeClock
    ) -> None:
        with pytest.raises(KeyError):
            self.failing_after_expiry(backend, clock, FRESH_S + 1, KeyError("bug"))

    def test_the_failure_types_can_be_chosen(self, backend: LocMemCache, clock: FakeClock) -> None:
        cache = StaleIfErrorCache(backend, clock)
        fetch(cache, Loader("old"))
        clock.advance(FRESH_S + 1)

        result = cache.get_or_load(
            "k",
            Loader(ValueError("odd")),
            fresh_ttl_s=FRESH_S,
            max_stale_age_s=MAX_STALE_S,
            catch=(ValueError,),
        )

        assert result == CacheResult("old", stale=True)

    def test_the_next_success_after_an_outage_is_fresh(
        self, backend: LocMemCache, clock: FakeClock
    ) -> None:
        cache = StaleIfErrorCache(backend, clock)
        fetch(cache, Loader("old"))
        clock.advance(FRESH_S + 1)
        assert fetch(cache, Loader(UpstreamUnavailable("p", "x"))).stale is True

        recovered = fetch(cache, Loader("new"))

        assert recovered == CacheResult("new", stale=False)

    def test_a_stale_hit_does_not_extend_the_entry(
        self, backend: LocMemCache, clock: FakeClock
    ) -> None:
        cache = StaleIfErrorCache(backend, clock)
        fetch(cache, Loader("old"))
        clock.advance(MAX_STALE_S - 10)
        assert fetch(cache, Loader(UpstreamUnavailable("p", "x"))).stale is True
        clock.advance(20)

        with pytest.raises(UpstreamUnavailable):
            fetch(cache, Loader(UpstreamUnavailable("p", "x")))


class BrokenBackend:
    """A cache backend that is down."""

    def get(self, key: str, default: object = None) -> object:
        raise ConnectionError("cache down")

    def set(self, key: str, value: object, timeout: object = None) -> None:
        raise ConnectionError("cache down")


class RecordingBackend:
    def __init__(self) -> None:
        self.sets: list[dict[str, Any]] = []

    def get(self, key: str, default: object = None) -> object:
        return default

    def set(self, key: str, value: object, timeout: object = None) -> None:
        self.sets.append({"key": key, "value": value, "timeout": timeout})


class TestBackendTrouble:
    def test_a_broken_cache_behaves_like_an_empty_one(self, clock: FakeClock) -> None:
        cache = StaleIfErrorCache(BrokenBackend(), clock)  # type: ignore[arg-type]
        loader = Loader("value")

        assert fetch(cache, loader) == CacheResult("value", stale=False)

    def test_upstream_errors_still_propagate_when_the_cache_is_broken(
        self, clock: FakeClock
    ) -> None:
        cache = StaleIfErrorCache(BrokenBackend(), clock)  # type: ignore[arg-type]

        with pytest.raises(UpstreamUnavailable):
            fetch(cache, Loader(UpstreamUnavailable("p", "down")))

    @pytest.mark.parametrize("garbage", ["text", 42, {"value": 1}, {"fetched_at": 1.0}, []])
    def test_unrecognised_entries_are_treated_as_misses(
        self, backend: LocMemCache, clock: FakeClock, garbage: object
    ) -> None:
        backend.set("k", garbage)
        loader = Loader("value")

        assert fetch(StaleIfErrorCache(backend, clock), loader).value == "value"
        assert loader.calls == 1

    def test_entries_expire_in_the_backend_when_the_stale_limit_is_reached(
        self, clock: FakeClock
    ) -> None:
        recorder = RecordingBackend()

        fetch(StaleIfErrorCache(recorder, clock), Loader("v"))  # type: ignore[arg-type]

        assert recorder.sets[0]["timeout"] == 21_600
        assert recorder.sets[0]["value"] == {"value": "v", "fetched_at": clock.now}


class TestKeys:
    def test_route_key_rounds_the_points_to_a_hundred_meters_or_so(self) -> None:
        key = route_key(LatLon(39.73921, -104.99028), LatLon(41.87811, -87.62980), "osrm")

        assert key == "truck:v1:route:osrm:39.739,-104.990:41.878,-87.630"

    def test_nearby_points_share_a_route_key_and_distant_ones_do_not(self) -> None:
        a = route_key(LatLon(39.73921, -104.99028), LatLon(41.87811, -87.6298), "osrm")
        close = route_key(LatLon(39.73949, -104.99049), LatLon(41.87839, -87.62951), "osrm")
        far = route_key(LatLon(39.7402, -104.99028), LatLon(41.87811, -87.6298), "osrm")

        assert a == close
        assert a != far

    def test_route_keys_depend_on_the_direction_and_the_provider(self) -> None:
        a, b = LatLon(39.739, -104.990), LatLon(41.878, -87.630)

        assert route_key(a, b, "osrm") != route_key(b, a, "osrm")
        assert route_key(a, b, "osrm") != route_key(a, b, "openrouteservice")

    def test_weather_key_rounds_to_a_tenth_of_a_degree(self) -> None:
        assert weather_key(LatLon(39.7392, -104.9903)) == "truck:v1:weather:39.7,-105.0"

    def test_lattice_points_and_nearby_points_share_a_weather_key(self) -> None:
        assert weather_key(LatLon(39.7, -105.0)) == weather_key(LatLon(39.74, -104.96))
        assert weather_key(LatLon(39.7, -105.0)) != weather_key(LatLon(39.8, -105.0))

    def test_negative_zero_is_not_written(self) -> None:
        key = weather_key(LatLon(-0.04, -0.01))

        assert key == "truck:v1:weather:0.0,0.0"
        assert "-0.0" not in key

    def test_southern_and_western_coordinates_keep_their_sign(self) -> None:
        assert weather_key(LatLon(-33.9, -70.7)) == "truck:v1:weather:-33.9,-70.7"

    def test_geocode_key_ignores_case_and_extra_whitespace(self) -> None:
        assert geocode_key("  Denver,   CO ", "photon") == geocode_key("denver, co", "photon")

    def test_geocode_keys_differ_by_query_and_provider(self) -> None:
        assert geocode_key("denver", "photon") != geocode_key("boulder", "photon")
        assert geocode_key("denver", "photon") != geocode_key("denver", "nominatim")

    def test_geocode_key_is_short_and_safe_whatever_the_query(self) -> None:
        key = geocode_key("São Paulo \n\t ✓ " + "x" * 500, "photon")

        assert len(key) < 80
        assert key.isascii()
        assert not any(char.isspace() for char in key)
