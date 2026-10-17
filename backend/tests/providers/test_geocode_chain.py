import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from django.core.cache.backends.locmem import LocMemCache

from planner.infra.cache import StaleIfErrorCache
from planner.infra.errors import (
    HostNotAllowed,
    UpstreamContractError,
    UpstreamError,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from planner.infra.http import ProviderPolicy, UpstreamClient
from planner.infra.resilience import MinSpacing
from planner.providers.geocode_chain import (
    CachedGeocoder,
    FallbackGeocodeProvider,
    build_geocoder,
)
from planner.providers.protocols import GeocodeProvider, Place, PlaceKind
from tests.infra.fakes import FakeClock, FixedJitter

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "geocode"
PHOTON = "photon.komoot.io"
NOMINATIM = "nominatim.openstreetmap.org"
ONE_DAY_S = 24 * 60 * 60  # the SPEC value, written out on purpose rather than imported
DENVER = Place("Denver, Colorado, United States", 39.74, -104.98, PlaceKind.CITY)
BOULDER = Place("Boulder, Colorado, United States", 40.01, -105.27, PlaceKind.CITY)


def fixture(name: str) -> Any:  # noqa: ANN401
    return json.loads((FIXTURES / f"{name}.json").read_text())


class Stub:
    """A geocoder that answers or raises, and records its queries."""

    def __init__(self, name: str, outcome: tuple[Place, ...] | Exception) -> None:
        self.name = name
        self.outcome = outcome
        self.queries: list[str] = []

    def search(self, query: str) -> tuple[Place, ...]:
        self.queries.append(query)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class TestFallbackGeocodeProvider:
    def test_the_first_provider_answers(self) -> None:
        first, second = Stub("photon", (DENVER,)), Stub("nominatim", (BOULDER,))

        assert FallbackGeocodeProvider([first, second]).search("denver") == (DENVER,)
        assert second.queries == []

    @pytest.mark.parametrize(
        "failure",
        [
            UpstreamUnavailable("photon", "down"),
            UpstreamTimeout("photon", "slow"),
            UpstreamContractError("photon", "garbage"),
        ],
        ids=["unavailable", "timeout", "contract-error"],
    )
    def test_the_next_provider_answers_when_the_first_fails(self, failure: Exception) -> None:
        first, second = Stub("photon", failure), Stub("nominatim", (BOULDER,))

        assert FallbackGeocodeProvider([first, second]).search("boulder") == (BOULDER,)
        assert (first.queries, second.queries) == (["boulder"], ["boulder"])

    def test_nothing_found_is_an_answer_and_ends_the_search(self) -> None:
        first, second = Stub("photon", ()), Stub("nominatim", (BOULDER,))

        assert FallbackGeocodeProvider([first, second]).search("zzzz") == ()
        assert second.queries == []

    @pytest.mark.parametrize(
        "error",
        [UpstreamError("photon", "HTTP 400", status=400), HostNotAllowed("host"), ValueError("q")],
    )
    def test_other_failures_are_raised_at_once(self, error: Exception) -> None:
        first, second = Stub("photon", error), Stub("nominatim", (BOULDER,))

        with pytest.raises(type(error)):
            FallbackGeocodeProvider([first, second]).search("denver")

        assert second.queries == []

    def test_when_every_provider_fails_the_last_failure_is_raised(self) -> None:
        first = Stub("photon", UpstreamUnavailable("photon", "down"))
        second = Stub("nominatim", UpstreamTimeout("nominatim", "slow"))

        with pytest.raises(UpstreamTimeout, match="nominatim"):
            FallbackGeocodeProvider([first, second]).search("denver")

    def test_needs_a_provider(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            FallbackGeocodeProvider([])


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(start=1_000_000.0)


@pytest.fixture
def cache(clock: FakeClock) -> Iterator[StaleIfErrorCache]:
    backend = LocMemCache(f"geocode-{uuid.uuid4()}", {})
    yield StaleIfErrorCache(backend, clock)
    backend.clear()


class TestCachedGeocoder:
    def test_a_repeated_query_is_answered_from_the_cache(self, cache: StaleIfErrorCache) -> None:
        provider = Stub("photon", (DENVER,))
        geocoder = CachedGeocoder(provider, cache)

        first = geocoder.search("denver")
        second = geocoder.search("denver")

        assert first == second == (DENVER,)
        assert provider.queries == ["denver"]

    def test_case_and_spacing_do_not_matter(self, cache: StaleIfErrorCache) -> None:
        provider = Stub("photon", (DENVER,))
        geocoder = CachedGeocoder(provider, cache)

        geocoder.search("Denver  CO")
        geocoder.search("  denver co ")
        geocoder.search("DENVER CO")

        assert len(provider.queries) == 1

    def test_the_provider_gets_the_cleaned_query(self, cache: StaleIfErrorCache) -> None:
        provider = Stub("photon", (DENVER,))

        CachedGeocoder(provider, cache).search("  New   York ")

        assert provider.queries == ["New York"]

    def test_different_queries_are_separate_entries(self, cache: StaleIfErrorCache) -> None:
        provider = Stub("photon", (DENVER,))
        geocoder = CachedGeocoder(provider, cache)

        geocoder.search("denver")
        geocoder.search("boulder")

        assert provider.queries == ["denver", "boulder"]

    def test_answers_are_kept_for_a_day_and_no_longer(
        self, cache: StaleIfErrorCache, clock: FakeClock
    ) -> None:
        provider = Stub("photon", (DENVER,))
        geocoder = CachedGeocoder(provider, cache)
        geocoder.search("denver")

        clock.advance(ONE_DAY_S - 1)
        geocoder.search("denver")
        assert len(provider.queries) == 1

        clock.advance(1)
        geocoder.search("denver")
        assert len(provider.queries) == 2

    def test_an_expired_answer_is_not_served_when_the_provider_fails(
        self, cache: StaleIfErrorCache, clock: FakeClock
    ) -> None:
        provider = Stub("photon", (DENVER,))
        geocoder = CachedGeocoder(provider, cache)
        geocoder.search("denver")
        clock.advance(ONE_DAY_S + 1)
        provider.outcome = UpstreamUnavailable("photon", "down")

        with pytest.raises(UpstreamUnavailable):
            geocoder.search("denver")

    def test_nothing_found_is_cached_too(self, cache: StaleIfErrorCache) -> None:
        provider = Stub("photon", ())
        geocoder = CachedGeocoder(provider, cache)

        assert geocoder.search("zzzz") == geocoder.search("zzzz") == ()
        assert len(provider.queries) == 1

    def test_a_failure_is_not_cached(self, cache: StaleIfErrorCache) -> None:
        provider = Stub("photon", UpstreamUnavailable("photon", "down"))
        geocoder = CachedGeocoder(provider, cache)
        with pytest.raises(UpstreamUnavailable):
            geocoder.search("denver")
        provider.outcome = (DENVER,)

        assert geocoder.search("denver") == (DENVER,)

    @pytest.mark.parametrize("query", ["", "ab", "x" * 101])
    def test_a_bad_query_reaches_neither_the_cache_nor_the_provider(
        self, cache: StaleIfErrorCache, query: str
    ) -> None:
        provider = Stub("photon", (DENVER,))

        with pytest.raises(ValueError, match="3 to 100"):
            CachedGeocoder(provider, cache).search(query)

        assert provider.queries == []

    def test_it_satisfies_the_geocode_provider_protocol(self, cache: StaleIfErrorCache) -> None:
        geocoder: GeocodeProvider = CachedGeocoder(Stub("photon", ()), cache)

        assert geocoder.name == "cached"


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


def real_client(clock: FakeClock, *, spaced: bool = False) -> UpstreamClient:
    gates = {"nominatim": MinSpacing(1.1, "nominatim", clock, clock.sleep)} if spaced else None
    return UpstreamClient(
        [
            ProviderPolicy("photon", timeout_s=4.0, max_concurrency=2),
            ProviderPolicy("nominatim", timeout_s=4.0, max_concurrency=2),
        ],
        [PHOTON, NOMINATIM],
        "tests/1.0",
        clock=clock,
        sleep=clock.sleep,
        jitter=FixedJitter(1.0),
        gates=gates,
    )


class TestBuildGeocoder:
    def test_photon_answers_first(
        self, api: respx.MockRouter, cache: StaleIfErrorCache, clock: FakeClock
    ) -> None:
        photon = api.get(host=PHOTON).respond(200, json=fixture("photon_city"))
        nominatim = api.get(host=NOMINATIM).respond(200, json=fixture("nominatim_city"))

        places = build_geocoder(real_client(clock), cache).search("denver")

        assert places[0].label == "Denver, Colorado, United States"
        assert photon.call_count == 1
        assert not nominatim.called

    def test_nominatim_answers_when_photon_is_down(
        self, api: respx.MockRouter, cache: StaleIfErrorCache, clock: FakeClock
    ) -> None:
        photon = api.get(host=PHOTON).respond(503)
        api.get(host=NOMINATIM).respond(200, json=fixture("nominatim_city"))

        places = build_geocoder(real_client(clock), cache).search("denver")

        assert [p.label for p in places][:2] == [
            "Denver, Colorado, United States",
            "Denver, Iowa, United States",
        ]
        assert photon.call_count == 2  # one try and its retry

    def test_nominatim_answers_when_photon_replies_with_garbage(
        self, api: respx.MockRouter, cache: StaleIfErrorCache, clock: FakeClock
    ) -> None:
        api.get(host=PHOTON).respond(200, json={"features": "none"})
        api.get(host=NOMINATIM).respond(200, json=fixture("nominatim_city"))

        assert len(build_geocoder(real_client(clock), cache).search("denver")) == 4

    def test_the_answer_of_the_fallback_is_cached_too(
        self, api: respx.MockRouter, cache: StaleIfErrorCache, clock: FakeClock
    ) -> None:
        photon = api.get(host=PHOTON).respond(503)
        nominatim = api.get(host=NOMINATIM).respond(200, json=fixture("nominatim_city"))
        geocoder = build_geocoder(real_client(clock), cache)

        geocoder.search("denver")
        geocoder.search("Denver")

        assert (photon.call_count, nominatim.call_count) == (2, 1)

    def test_both_providers_down_is_an_error(
        self, api: respx.MockRouter, cache: StaleIfErrorCache, clock: FakeClock
    ) -> None:
        api.get(host=PHOTON).respond(503)
        api.get(host=NOMINATIM).mock(side_effect=httpx.ReadTimeout("slow"))

        with pytest.raises(UpstreamTimeout):
            build_geocoder(real_client(clock), cache).search("denver")

    def test_nothing_found_by_photon_is_not_searched_again_on_nominatim(
        self, api: respx.MockRouter, cache: StaleIfErrorCache, clock: FakeClock
    ) -> None:
        api.get(host=PHOTON).respond(200, json=fixture("photon_empty"))
        nominatim = api.get(host=NOMINATIM).respond(200, json=fixture("nominatim_city"))

        assert build_geocoder(real_client(clock), cache).search("qzxwvbnmpl") == ()
        assert not nominatim.called

    def test_nominatim_requests_are_kept_a_second_apart(
        self, api: respx.MockRouter, cache: StaleIfErrorCache, clock: FakeClock
    ) -> None:
        api.get(host=PHOTON).respond(503)
        api.get(host=NOMINATIM).respond(200, json=fixture("nominatim_city"))
        geocoder = build_geocoder(real_client(clock, spaced=True), cache)

        geocoder.search("denver")
        assert clock.sleeps == [pytest.approx(0.3)]  # Photon's retry backoff; Nominatim not delayed

        geocoder.search("boulder")

        # Photon's backoff again, then the rest of the 1.1 s since the previous Nominatim request.
        assert clock.sleeps == [pytest.approx(0.3), pytest.approx(0.3), pytest.approx(0.8)]
