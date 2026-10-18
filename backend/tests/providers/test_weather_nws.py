import copy
import json
import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from django.core.cache.backends.locmem import LocMemCache

from planner.domain.models import LatLon
from planner.infra.cache import StaleIfErrorCache
from planner.infra.errors import UpstreamContractError
from planner.infra.http import ProviderPolicy, UpstreamClient
from planner.infra.resilience import deadline_scope
from planner.providers.protocols import WeatherProvider
from planner.providers.weather_nws import NwsWeatherProvider, convert_grid
from tests.infra.fakes import FakeClock, FixedJitter

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "nws"
HOST = "api.weather.gov"
POINTS_URL = f"https://{HOST}/points/40.0,-105.3"
GRID_URL = f"https://{HOST}/gridpoints/BOU/53,74"
DAY = date(2026, 10, 18)
BOULDER = LatLon(40.0, -105.3)
LOGGER = "planner.providers.weather_nws"


def fixture(name: str) -> Any:  # noqa: ANN401
    return json.loads((FIXTURES / f"{name}.json").read_text())


def properties(name: str) -> dict[str, Any]:
    return dict(fixture(name)["properties"])


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(start=1_000_000.0)


class Setup:
    """A provider wired to a real client and cache, both on one fake clock."""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.backend = LocMemCache(f"nws-{uuid.uuid4()}", {})
        self.cache = StaleIfErrorCache(self.backend, clock)
        self.client = UpstreamClient(
            [ProviderPolicy("nws", timeout_s=8.0, max_concurrency=12)],
            [HOST],
            "tests/1.0",
            clock=clock,
            sleep=clock.sleep,
            jitter=FixedJitter(0.0),
        )
        self.provider = NwsWeatherProvider(self.client, self.cache)

    def close(self) -> None:
        self.backend.clear()


@pytest.fixture
def setup(clock: FakeClock) -> Iterator[Setup]:
    stack = Setup(clock)
    yield stack
    stack.close()


def serve(api: respx.MockRouter) -> tuple[respx.Route, respx.Route]:
    points = api.get(POINTS_URL).respond(200, json=fixture("points_boulder"))
    grid = api.get(GRID_URL).respond(200, json=fixture("gridpoints_boulder"))
    return points, grid


class TestConversion:
    """The one place where NWS units and intervals become the domain's hourly mph and in/hr."""

    def storm(self) -> Any:  # noqa: ANN401
        series = convert_grid(properties("gridpoints_storm"), DAY, DAY)
        assert series is not None
        return series

    def test_wind_and_gusts_become_mph(self) -> None:
        series = self.storm()

        assert series.wind_mph[12:15] == pytest.approx((45.0, 45.0, 45.0))  # 72.42048 km/h over 3 h
        assert series.gust_mph[12:15] == pytest.approx((60.0, 60.0, 60.0))  # 96.56064 km/h

    def test_a_missing_value_stays_unknown_and_so_do_hours_nothing_covers(self) -> None:
        series = self.storm()

        assert series.wind_mph[15] is None  # the forecast has no value for that hour
        assert series.wind_mph[11] is None  # nothing covers the hours around the storm
        assert series.wind_mph[16] is None
        assert len(series) == 24

    def test_precipitation_is_spread_over_its_interval_and_follows_the_hour_it_covers(self) -> None:
        series = self.storm()

        # 15.24 mm (0.6 in) over the six hours from 12:00; the value at hour h covers the hour
        # before h, as with Open-Meteo, so the six values sit at 13:00 to 18:00.
        assert series.snowfall_in[13:19] == pytest.approx((0.5,) * 6)  # 76.2 mm of snow over 6 h
        assert series.snowfall_in[12] is None
        assert series.snowfall_in[19] is None

    def test_the_rain_is_what_is_left_after_the_snow_has_melted(self) -> None:
        series = self.storm()

        # 0.1 in/hr of precipitation in all, of which 0.5 in/hr of snow is 0.05 in/hr of water.
        assert series.rain_in[13:19] == pytest.approx((0.05,) * 6)
        assert series.showers_in[13:19] == (0.0,) * 6

    def test_snow_cannot_make_the_rain_negative(self) -> None:
        grid = properties("gridpoints_storm")
        grid["quantitativePrecipitation"]["values"][0]["value"] = 1.0  # less water than the snow

        series = convert_grid(grid, DAY, DAY)

        assert series is not None
        assert series.rain_in[13] == 0.0

    def test_there_is_no_weather_code(self) -> None:
        assert set(self.storm().weather_code) == {None}

    def test_the_recorded_forecast_covers_the_days_asked_for(self) -> None:
        series = convert_grid(properties("gridpoints_boulder"), DAY, date(2026, 10, 20))

        assert series is not None
        assert series.start == datetime(2026, 10, 18, tzinfo=UTC)
        assert len(series) == 72
        assert series.wind_mph[0] == pytest.approx(1.852 / 1.609344)
        assert all(value is not None for value in series.wind_mph)

    def test_hours_before_the_first_day_are_not_part_of_the_series(self) -> None:
        series = convert_grid(
            properties("gridpoints_boulder"), date(2026, 10, 19), date(2026, 10, 19)
        )

        assert series is not None
        assert series.start == datetime(2026, 10, 19, tzinfo=UTC)
        assert len(series) == 24

    def test_a_forecast_without_wind_for_those_days_is_no_series(self) -> None:
        assert (
            convert_grid(properties("gridpoints_boulder"), date(2026, 12, 1), date(2026, 12, 1))
            is None
        )

    @pytest.mark.parametrize(
        "name", ["windSpeed", "windGust", "quantitativePrecipitation", "snowfallAmount"]
    )
    def test_other_units_are_a_contract_error_and_nothing_is_converted(self, name: str) -> None:
        grid = properties("gridpoints_storm")
        grid[name]["uom"] = "wmoUnit:m_s-1"

        with pytest.raises(UpstreamContractError, match=name):
            convert_grid(grid, DAY, DAY)

    @pytest.mark.parametrize(
        "valid_time",
        [
            "2026-10-18T12:00:00/PT3H",  # no zone
            "2026-10-18T12:30:00+00:00/PT3H",  # not on the hour
            "not a time/PT3H",
            "2026-10-18T12:00:00+00:00/PT",  # no length
            "2026-10-18T12:00:00+00:00",  # no duration at all
            "2026-10-18T12:00:00+00:00/3 hours",
        ],
    )
    def test_an_interval_it_cannot_read_is_a_contract_error(self, valid_time: str) -> None:
        grid = properties("gridpoints_storm")
        grid["windSpeed"]["values"] = [{"validTime": valid_time, "value": 10.0}]

        with pytest.raises(UpstreamContractError):
            convert_grid(grid, DAY, DAY)

    def test_an_interval_may_run_for_days(self) -> None:
        grid = properties("gridpoints_storm")
        grid["windSpeed"]["values"] = [
            {"validTime": "2026-10-18T00:00:00+00:00/P1DT2H", "value": 16.09344}
        ]

        series = convert_grid(grid, DAY, date(2026, 10, 19))

        assert series is not None
        assert series.wind_mph[:26] == pytest.approx((10.0,) * 26)
        assert series.wind_mph[26] is None

    @pytest.mark.parametrize(
        "missing", ["windSpeed", "windGust", "quantitativePrecipitation", "snowfallAmount"]
    )
    def test_a_forecast_without_a_variable_is_a_contract_error(self, missing: str) -> None:
        grid = properties("gridpoints_storm")
        del grid[missing]

        with pytest.raises(UpstreamContractError):
            convert_grid(grid, DAY, DAY)

    def test_the_values_are_not_changed_in_the_input(self) -> None:
        grid = properties("gridpoints_storm")
        before = copy.deepcopy(grid)

        convert_grid(grid, DAY, DAY)

        assert grid == before


class TestProvider:
    def test_returns_a_series_for_the_place_keyed_by_the_rounded_place(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        serve(api)

        result = setup.provider.hourly([LatLon(40.03, -105.27)], DAY, date(2026, 10, 20))

        assert list(result.series) == [BOULDER]
        assert result.series[BOULDER] is not None
        assert (result.source, result.stale, result.missing) == ("nws", False, 0)

    def test_it_asks_for_the_point_to_a_tenth_of_a_degree_and_then_for_its_grid(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        points, grid = serve(api)

        setup.provider.hourly([LatLon(40.03, -105.27)], DAY, DAY)

        assert (points.call_count, grid.call_count) == (1, 1)
        assert points.calls.last.request.headers["User-Agent"] == "tests/1.0"

    def test_places_that_round_to_the_same_cell_make_one_request(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        points, _ = serve(api)

        result = setup.provider.hourly([LatLon(40.01, -105.31), LatLon(39.96, -105.26)], DAY, DAY)

        assert points.call_count == 1
        assert len(result.series) == 1

    def test_a_second_request_makes_no_call(self, api: respx.MockRouter, setup: Setup) -> None:
        points, grid = serve(api)
        setup.provider.hourly([BOULDER], DAY, DAY)

        setup.provider.hourly([BOULDER], DAY, DAY)

        assert (points.call_count, grid.call_count) == (1, 1)

    def test_another_day_range_asks_for_the_forecast_again_but_not_for_the_grid_cell(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        points, grid = serve(api)
        setup.provider.hourly([BOULDER], DAY, DAY)

        setup.provider.hourly([BOULDER], DAY, date(2026, 10, 19))

        assert (points.call_count, grid.call_count) == (1, 2)

    def test_a_series_is_fresh_for_thirty_minutes(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        _, grid = serve(api)
        setup.provider.hourly([BOULDER], DAY, DAY)

        setup.clock.advance(29 * 60)
        setup.provider.hourly([BOULDER], DAY, DAY)
        assert grid.call_count == 1

        setup.clock.advance(2 * 60)
        setup.provider.hourly([BOULDER], DAY, DAY)
        assert grid.call_count == 2

    def test_no_places_means_no_calls(self, api: respx.MockRouter, setup: Setup) -> None:
        points, grid = serve(api)

        result = setup.provider.hourly([], DAY, DAY)

        assert result.series == {}
        assert not points.called
        assert not grid.called

    @pytest.mark.parametrize(
        ("first", "last"), [(date(2026, 10, 19), DAY), (DAY, date(2026, 10, 26))]
    )
    def test_invalid_day_ranges_are_refused(self, setup: Setup, first: date, last: date) -> None:
        with pytest.raises(ValueError, match="day"):
            setup.provider.hourly([BOULDER], first, last)

    def test_eight_days_are_allowed(self, api: respx.MockRouter, setup: Setup) -> None:
        serve(api)

        result = setup.provider.hourly([BOULDER], DAY, date(2026, 10, 25))

        assert result.missing == 0

    def test_it_satisfies_the_weather_provider_protocol(self, setup: Setup) -> None:
        provider: WeatherProvider = setup.provider

        assert provider.name == "nws"


class TestGaps:
    def test_a_place_outside_the_service_area_has_no_weather_and_is_not_an_error(
        self, api: respx.MockRouter, setup: Setup, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING, logger=LOGGER)
        api.get(POINTS_URL).respond(404, json={"title": "Data Unavailable For Requested Point"})

        result = setup.provider.hourly([BOULDER], DAY, DAY)

        assert result.series == {BOULDER: None}
        assert result.missing == 1
        assert "nws lost weather for 1 of 1 places: 1 x HTTP 404" in caplog.text

    def test_an_outage_degrades_to_missing_weather(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        api.get(POINTS_URL).respond(503)

        result = setup.provider.hourly([BOULDER], DAY, DAY)

        assert (result.series, result.stale, result.missing) == ({BOULDER: None}, False, 1)

    def test_stale_series_are_served_and_flagged_when_the_service_fails(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        serve(api)
        fresh = setup.provider.hourly([BOULDER], DAY, DAY)
        setup.clock.advance(31 * 60)
        api.get(GRID_URL).respond(503)

        result = setup.provider.hourly([BOULDER], DAY, DAY)

        assert result.series == fresh.series
        assert (result.stale, result.missing) == (True, 0)

    def test_after_six_hours_the_place_comes_back_without_weather(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        serve(api)
        setup.provider.hourly([BOULDER], DAY, DAY)
        setup.clock.advance(6 * 3600 + 1)
        api.get(GRID_URL).respond(503)

        result = setup.provider.hourly([BOULDER], DAY, DAY)

        assert (result.stale, result.missing) == (False, 1)

    def test_the_lost_places_are_logged_once_together_not_one_line_each(
        self, api: respx.MockRouter, setup: Setup, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING, logger=LOGGER)
        api.get(host=HOST).respond(503)
        places = [LatLon(40.0, -105.0 + index * 0.1) for index in range(5)]

        setup.provider.hourly(places, DAY, DAY)

        (record,) = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert "nws lost weather for 5 of 5 places: 5 x HTTP 503" in record.getMessage()

    def test_a_place_naming_a_grid_on_another_host_is_refused(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        points = copy.deepcopy(fixture("points_boulder"))
        points["properties"]["forecastGridData"] = "https://example.com/gridpoints/BOU/53,74"
        api.get(POINTS_URL).respond(200, json=points)

        result = setup.provider.hourly([BOULDER], DAY, DAY)

        assert result.missing == 1

    def test_an_answer_it_cannot_read_leaves_the_place_unknown_instead_of_failing_the_plan(
        self, api: respx.MockRouter, setup: Setup, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING, logger=LOGGER)
        api.get(POINTS_URL).respond(200, json=fixture("points_boulder"))
        api.get(GRID_URL).respond(200, json={"properties": {"windSpeed": "fast"}})

        result = setup.provider.hourly([BOULDER], DAY, DAY)

        assert result.missing == 1
        assert "windSpeed is not an object" in caplog.text

    @pytest.mark.parametrize("body", [[], {"properties": []}, {}])
    def test_a_point_answer_of_the_wrong_shape_leaves_the_place_unknown(
        self,
        api: respx.MockRouter,
        setup: Setup,
        body: Any,  # noqa: ANN401
    ) -> None:
        api.get(POINTS_URL).respond(200, json=body)

        assert setup.provider.hourly([BOULDER], DAY, DAY).missing == 1

    def test_an_exhausted_request_deadline_degrades_to_missing_weather(
        self, api: respx.MockRouter, setup: Setup, clock: FakeClock
    ) -> None:
        points, _ = serve(api)

        with deadline_scope(5.0, clock):
            clock.advance(6.0)
            result = setup.provider.hourly([BOULDER], DAY, DAY)

        assert not points.called
        assert result.missing == 1

    def test_the_circuit_opens_after_repeated_failures_and_later_places_are_not_asked(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        route = api.get(host=HOST).mock(return_value=httpx.Response(503))
        places = [LatLon(40.0, -105.0 + index * 0.1) for index in range(20)]

        setup.provider.hourly(places, DAY, DAY)
        calls = route.call_count
        setup.provider.hourly(places, DAY, DAY)

        assert route.call_count == calls  # the breaker is open: the second round asks nobody
