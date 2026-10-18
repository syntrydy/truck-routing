import logging
from collections.abc import Sequence
from datetime import date

import pytest

from planner.domain.models import LatLon
from planner.infra.errors import UpstreamUnavailable
from planner.providers.protocols import WeatherProvider, WeatherResult
from planner.providers.weather_chain import FallbackWeatherProvider
from tests.services.stubs import StubWeather

DAY = date(2026, 10, 18)
A, B, C, D = LatLon(40.0, -105.0), LatLon(40.1, -105.0), LatLon(40.2, -105.0), LatLon(40.3, -105.0)


def provider(
    name: str, known: set[LatLon], *, stale: bool = False, **conditions: float
) -> StubWeather:
    """A stub that has weather (with the given conditions) for the places in ``known`` only."""
    stub = StubWeather(lambda place: conditions if place in known else None, stale=stale)
    stub.name = name
    return stub


class Failing:
    name = "failing"

    def hourly(self, points: Sequence[LatLon], first_day: date, last_day: date) -> WeatherResult:
        raise UpstreamUnavailable("failing", "circuit open")


def chain(primary: WeatherProvider, secondary: WeatherProvider) -> FallbackWeatherProvider:
    return FallbackWeatherProvider(primary, secondary)


class TestFallback:
    def test_a_primary_that_has_everything_is_the_only_one_asked(self) -> None:
        primary, secondary = provider("main", {A, B}), provider("backup", {A, B})

        result = chain(primary, secondary).hourly([A, B], DAY, DAY)

        assert secondary.calls == []
        assert result.source == "stub-weather"
        assert result.missing == 0

    def test_the_secondary_is_asked_only_for_the_places_the_primary_lacks_in_order(self) -> None:
        primary, secondary = provider("main", {A, C}), provider("backup", {B, D})

        chain(primary, secondary).hourly([A, B, C, D], DAY, DAY)

        (asked, first_day, last_day) = secondary.calls[0]
        assert asked == [B, D]
        assert (first_day, last_day) == (DAY, DAY)

    def test_the_gaps_are_filled_and_the_primary_keeps_what_it_had(self) -> None:
        primary = provider("main", {A}, wind=10.0)
        secondary = provider("backup", {B}, wind=20.0)

        result = chain(primary, secondary).hourly([A, B], DAY, DAY)

        assert list(result.series) == [A, B]
        kept, filled = result.series[A], result.series[B]
        assert kept is not None
        assert kept.wind_mph[0] == 10.0
        assert filled is not None
        assert filled.wind_mph[0] == 20.0
        assert result.missing == 0

    def test_when_both_supplied_part_the_source_names_both(self) -> None:
        result = chain(provider("main", {A}), provider("backup", {B})).hourly([A, B], DAY, DAY)

        assert result.source == "main+backup"

    def test_when_the_secondary_supplied_everything_the_source_is_the_secondary(self) -> None:
        result = chain(provider("main", set()), provider("backup", {A, B})).hourly([A, B], DAY, DAY)

        assert result.source == "backup"
        assert result.missing == 0

    def test_places_neither_has_stay_unknown_and_are_counted(self) -> None:
        result = chain(provider("main", {A}), provider("backup", {B})).hourly([A, B, C], DAY, DAY)

        assert result.series[C] is None
        assert result.missing == 1

    def test_a_secondary_that_supplies_nothing_changes_nothing(self) -> None:
        primary = provider("main", {A})

        result = chain(primary, provider("backup", set())).hourly([A, B], DAY, DAY)

        assert result.source == "stub-weather"  # the primary's own answer, untouched
        assert result.missing == 1

    def test_a_secondary_that_fails_leaves_the_primarys_answer(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.ERROR, logger="planner.providers.weather_chain")

        result = chain(provider("main", {A}), Failing()).hourly([A, B], DAY, DAY)

        assert result.series[A] is not None
        assert result.series[B] is None
        assert "failing could not fill the gaps left by main" in caplog.text

    def test_stale_if_either_was(self) -> None:
        result = chain(
            provider("main", {A}, stale=False), provider("backup", {B}, stale=True)
        ).hourly([A, B], DAY, DAY)

        assert result.stale is True

    def test_a_primary_that_fails_is_not_hidden(self) -> None:
        with pytest.raises(UpstreamUnavailable):
            chain(Failing(), provider("backup", {A})).hourly([A], DAY, DAY)

    def test_it_names_itself_after_both(self) -> None:
        assert chain(provider("main", set()), provider("backup", set())).name == "main+backup"
