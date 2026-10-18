"""The recorded corridor and storm that the demo replays."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from planner.domain.models import LatLon
from planner.providers.protocols import NoRoute
from planner.providers.recorded import (
    DEMO_DESTINATION,
    DEMO_ORIGIN,
    SOURCE,
    STORM_START_HOUR,
    DemoScenario,
    RecordedRouting,
    RecordedWeather,
    load_scenario,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "demo"
DEPARTURE_HOUR = datetime(2026, 10, 18, 14, 0, tzinfo=UTC)
LARAMIE = LatLon(41.3, -105.6)


@pytest.fixture(scope="module")
def scenario() -> DemoScenario:
    return load_scenario(FIXTURES)


class TestTheScenario:
    def test_it_has_three_roads_from_denver_to_salt_lake_city(self, scenario: DemoScenario) -> None:
        assert len(scenario.routes) == 3
        for route in scenario.routes:
            assert route.points[0].lat == pytest.approx(DEMO_ORIGIN.lat, abs=0.2)
            assert route.points[-1].lon == pytest.approx(DEMO_DESTINATION.lon, abs=0.2)
            assert len(route.segment_durations_s) == len(route.points) - 1
            assert sum(route.segment_durations_s) == pytest.approx(route.duration_s)

    def test_the_weather_covers_every_route(self, scenario: DemoScenario) -> None:
        assert len(scenario.places) >= 20
        assert all(len(place.series.wind_mph) == 144 for place in scenario.places)


class TestRecordedRouting:
    def test_the_roads_come_fastest_first_from_the_demo(self, scenario: DemoScenario) -> None:
        result = RecordedRouting(scenario).routes(DEMO_ORIGIN, DEMO_DESTINATION)

        durations = [route.duration_s for route in result.routes]
        assert durations == sorted(durations)
        assert result.source == SOURCE
        assert result.snap_distance_m == 0

    def test_there_are_no_detours_to_ask_for(self, scenario: DemoScenario) -> None:
        with pytest.raises(NoRoute):
            RecordedRouting(scenario).route_via(DEMO_ORIGIN, LARAMIE, DEMO_DESTINATION)


class TestRecordedWeather:
    def test_the_storm_starts_at_the_departure_hour(self, scenario: DemoScenario) -> None:
        weather = RecordedWeather(scenario, DEPARTURE_HOUR)
        day = DEPARTURE_HOUR.date()

        series = weather.hourly([LARAMIE], day, day + timedelta(days=1)).series[LARAMIE]

        assert series is not None
        nearest = min(
            scenario.places,
            key=lambda p: (p.location.lat - LARAMIE.lat) ** 2 + (p.location.lon - LARAMIE.lon) ** 2,
        )
        for hours_after in (0, 3, 20):
            recorded = nearest.series.wind_mph[STORM_START_HOUR + hours_after]
            replayed = series.wind_mph[series_index(series.start, DEPARTURE_HOUR, hours_after)]
            assert replayed == recorded

    def test_a_trip_into_the_storm_meets_severe_wind(self, scenario: DemoScenario) -> None:
        weather = RecordedWeather(scenario, DEPARTURE_HOUR)
        day = DEPARTURE_HOUR.date()

        series = weather.hourly([LARAMIE], day, day + timedelta(days=2)).series[LARAMIE]

        assert series is not None
        assert max(w for w in series.wind_mph if w is not None) >= 45

    def test_hours_the_recording_does_not_cover_are_unknown(self, scenario: DemoScenario) -> None:
        weather = RecordedWeather(scenario, DEPARTURE_HOUR)
        last = date(2026, 10, 18) + timedelta(days=7)

        result = weather.hourly([LARAMIE], date(2026, 10, 18), last)

        series = result.series[LARAMIE]
        assert series is not None
        assert series.wind_mph[-1] is None
        assert result.source == SOURCE
        assert not result.stale

    def test_every_place_gets_a_series(self, scenario: DemoScenario) -> None:
        weather = RecordedWeather(scenario, DEPARTURE_HOUR)
        places = [LatLon(39.7, -105.0), LatLon(41.0, -110.0), LatLon(45.0, -100.0)]

        result = weather.hourly(places, date(2026, 10, 18), date(2026, 10, 18))

        assert result.missing == 0
        assert set(result.series) == set(places)


def series_index(start: datetime, departure: datetime, hours_after: int) -> int:
    """Where the hour ``hours_after`` the departure sits in a series starting at ``start``."""
    return int((departure - start).total_seconds() // 3600) + hours_after
