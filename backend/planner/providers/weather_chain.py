"""Asking weather providers in turn (SPEC section 6: the NWS fills what Open-Meteo lacks)."""

import logging
from collections.abc import Sequence
from datetime import date

from planner.domain.models import HourlySeries, LatLon
from planner.infra.cache import StaleIfErrorCache
from planner.infra.errors import UpstreamError
from planner.infra.http import UpstreamClient
from planner.providers.protocols import WeatherProvider, WeatherResult
from planner.providers.weather_nws import NwsWeatherProvider
from planner.providers.weather_openmeteo import OpenMeteoWeatherProvider

logger = logging.getLogger(__name__)


class FallbackWeatherProvider:
    """Weather from ``primary``, with ``secondary`` asked only for the places it could not supply.

    The result's ``source`` names who answered: the primary alone, the secondary alone, or both
    (for example ``open-meteo+nws``). A place neither could supply stays ``None`` (unknown).
    """

    def __init__(self, primary: WeatherProvider, secondary: WeatherProvider) -> None:
        self._primary = primary
        self._secondary = secondary
        self.name = f"{primary.name}+{secondary.name}"

    def hourly(self, points: Sequence[LatLon], first_day: date, last_day: date) -> WeatherResult:
        first = self._primary.hourly(points, first_day, last_day)
        # Keep the order the caller gave, which puts the places that matter most first.
        gaps = [place for place, series in first.series.items() if series is None]
        if not gaps:
            return first
        try:
            second = self._secondary.hourly(gaps, first_day, last_day)
        except UpstreamError:
            logger.exception(
                "%s could not fill the gaps left by %s", self._secondary.name, self._primary.name
            )
            return first
        filled = {place: series for place, series in second.series.items() if series is not None}
        if not filled:
            return first
        series: dict[LatLon, HourlySeries | None] = {
            place: first.series[place] if place not in filled else filled[place]
            for place in first.series
        }
        return WeatherResult(
            series=series,
            source=self._secondary.name if len(filled) == len(first.series) else self.name,
            stale=first.stale or second.stale,
            missing=sum(1 for value in series.values() if value is None),
        )


def build_weather_provider(client: UpstreamClient, cache: StaleIfErrorCache) -> WeatherProvider:
    """Open-Meteo, with the National Weather Service behind it for the United States."""
    return FallbackWeatherProvider(
        OpenMeteoWeatherProvider(client, cache), NwsWeatherProvider(client, cache)
    )
