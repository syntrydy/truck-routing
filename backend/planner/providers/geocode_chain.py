"""Geocoding as the application uses it: Photon, then Nominatim, with a 24 hour cache."""

from collections.abc import Sequence

from planner.infra.cache import StaleIfErrorCache, geocode_key
from planner.infra.http import UpstreamClient
from planner.providers.fallback import first_success
from planner.providers.geocode_nominatim import NominatimGeocoder
from planner.providers.geocode_photon import PhotonGeocoder
from planner.providers.protocols import GeocodeProvider, Place, normalize_query

CACHE_TTL_S = 24 * 60 * 60
CACHE_PROVIDER_KEY = "geocode"  # results are cached whichever provider produced them


class FallbackGeocodeProvider:
    """Asks each geocoder in turn and returns the first answer.

    Both an outage and a response that cannot be read move on to the next geocoder; an empty
    answer ("nothing found") is an answer and ends the search. If every geocoder fails, the
    last failure is raised.
    """

    name = "fallback"

    def __init__(self, providers: Sequence[GeocodeProvider]) -> None:
        if not providers:
            msg = "at least one geocoding provider is required"
            raise ValueError(msg)
        self._providers = tuple(providers)

    def search(self, query: str) -> tuple[Place, ...]:
        return first_success(self._providers, lambda provider: provider.search(query))


class CachedGeocoder:
    """Remembers answers for 24 hours, whatever the case or spacing of the query."""

    name = "cached"

    def __init__(self, provider: GeocodeProvider, cache: StaleIfErrorCache) -> None:
        self._provider = provider
        self._cache = cache

    def search(self, query: str) -> tuple[Place, ...]:
        cleaned = normalize_query(query)  # a bad query never reaches the cache or a provider
        result = self._cache.get_or_load(
            geocode_key(cleaned, CACHE_PROVIDER_KEY),
            lambda: self._provider.search(cleaned),
            fresh_ttl_s=CACHE_TTL_S,
            max_stale_age_s=CACHE_TTL_S,  # nothing older than a day is served, even on failure
        )
        return result.value


def build_geocoder(client: UpstreamClient, cache: StaleIfErrorCache) -> GeocodeProvider:
    """Photon with Nominatim behind it, cached."""
    return CachedGeocoder(
        FallbackGeocodeProvider([PhotonGeocoder(client), NominatimGeocoder(client)]), cache
    )
