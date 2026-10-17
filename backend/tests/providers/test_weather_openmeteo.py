import copy
import json
import threading
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from django.core.cache.backends.locmem import LocMemCache

from planner.domain.models import HourlySeries, LatLon
from planner.infra.cache import StaleIfErrorCache
from planner.infra.errors import UpstreamContractError, UpstreamError
from planner.infra.http import ProviderPolicy, UpstreamClient
from planner.infra.resilience import deadline_scope
from planner.providers.protocols import WeatherProvider, rounded_point
from planner.providers.weather_openmeteo import OpenMeteoWeatherProvider
from tests.infra.fakes import FakeClock, FixedJitter

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "openmeteo"
HOST = "api.open-meteo.com"
URL = f"https://{HOST}/v1/forecast"
FIRST_DAY, LAST_DAY = date(2026, 10, 18), date(2026, 10, 20)
SEATTLE, RAINIER, LOVELAND, MINNEAPOLIS = (
    LatLon(47.6, -122.3),
    LatLon(46.8, -121.7),
    LatLon(39.7, -105.9),
    LatLon(44.9, -93.3),
)
FOUR_PLACES = [SEATTLE, RAINIER, LOVELAND, MINNEAPOLIS]
DENVER = LatLon(39.7, -105.0)


def fixture(name: str) -> Any:  # noqa: ANN401
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(start=1_000_000.0)


class Setup:
    """A provider wired to a real client and cache, both on one fake clock."""

    def __init__(self, clock: FakeClock, client_concurrency: int = 4) -> None:
        self.clock = clock
        self.backend = LocMemCache(f"weather-{uuid.uuid4()}", {})
        self.cache = StaleIfErrorCache(self.backend, clock)
        self.client = UpstreamClient(
            [ProviderPolicy("open-meteo", timeout_s=10.0, max_concurrency=client_concurrency)],
            [HOST],
            "tests/1.0",
            clock=clock,
            sleep=clock.sleep,
            jitter=FixedJitter(0.0),
        )
        self.provider = OpenMeteoWeatherProvider(self.client, self.cache)

    def close(self) -> None:
        self.backend.clear()


@pytest.fixture
def setup(clock: FakeClock) -> Iterator[Setup]:
    stack = Setup(clock)
    yield stack
    stack.close()


class Replier:
    """Answers each request with one copy of the recorded place per requested latitude."""

    def __init__(self, delay_s: float = 0.0) -> None:
        self.template = fixture("single_point")
        self.delay_s = delay_s
        self.sizes: list[int] = []
        self.requests: list[httpx.Request] = []
        self._lock = threading.Lock()
        self._in_flight = 0
        self.max_in_flight = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        count = len(request.url.params["latitude"].split(","))
        with self._lock:
            self.sizes.append(count)
            self.requests.append(request)
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            if self.delay_s:
                time.sleep(self.delay_s)
            places = [copy.deepcopy(self.template) for _ in range(count)]
            return httpx.Response(200, json=places if count > 1 else places[0])
        finally:
            with self._lock:
                self._in_flight -= 1


def grid(count: int) -> list[LatLon]:
    """``count`` distinct places that stay distinct after rounding to 0.1 degrees."""
    return [
        LatLon(20.0 + (index // 100) * 0.1, -120.0 + (index % 100) * 0.1) for index in range(count)
    ]


class TestRecordedResponses:
    def test_returns_a_series_per_place_keyed_by_the_rounded_place(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        api.get(URL).respond(200, json=fixture("four_points"))

        result = setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY)

        assert result.source == "open-meteo"
        assert list(result.series) == FOUR_PLACES
        assert (result.stale, result.missing) == (False, 0)
        for series in result.series.values():
            assert isinstance(series, HourlySeries)
            assert len(series) == 72

    def test_each_place_gets_its_own_recorded_values(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        recorded = fixture("four_points")
        api.get(URL).respond(200, json=recorded)

        result = setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY)

        for place, raw in zip(FOUR_PLACES, recorded, strict=True):
            series = result.series[place]
            assert series is not None
            assert series.wind_mph == tuple(raw["hourly"]["wind_speed_10m"])
            assert series.gust_mph == tuple(raw["hourly"]["wind_gusts_10m"])
            assert series.rain_in == tuple(raw["hourly"]["rain"])
            assert series.showers_in == tuple(raw["hourly"]["showers"])
            assert series.snowfall_in == tuple(raw["hourly"]["snowfall"])
            assert series.weather_code == tuple(raw["hourly"]["weather_code"])
            assert series.start == datetime(2026, 10, 18, tzinfo=UTC)

    def test_real_drizzle_is_carried_through(self, api: respx.MockRouter, setup: Setup) -> None:
        api.get(URL).respond(200, json=fixture("four_points"))

        loveland = setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY).series[LOVELAND]

        assert loveland is not None
        assert max(value for value in loveland.rain_in if value is not None) > 0
        assert 51 in loveland.weather_code

    def test_results_follow_the_request_not_the_grid_cell_the_server_reports(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        recorded = fixture("four_points")
        api.get(URL).respond(200, json=recorded)

        result = setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY)

        assert recorded[2]["latitude"] != LOVELAND.lat  # 39.71 came back for 39.7
        assert result.series[LOVELAND] is not None
        assert LatLon(recorded[2]["latitude"], recorded[2]["longitude"]) not in result.series

    def test_a_single_place_arrives_as_an_object(self, api: respx.MockRouter, setup: Setup) -> None:
        api.get(URL).respond(200, json=fixture("single_point"))

        result = setup.provider.hourly([DENVER], FIRST_DAY, LAST_DAY)

        assert isinstance(result.series[DENVER], HourlySeries)

    def test_the_request_asks_for_the_agreed_variables_units_and_days(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        route = api.get(URL).respond(200, json=fixture("four_points"))

        setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY)

        assert dict(route.calls.last.request.url.params) == {
            "latitude": "47.6,46.8,39.7,44.9",
            "longitude": "-122.3,-121.7,-105.9,-93.3",
            "hourly": "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall,weather_code",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timeformat": "unixtime",
            "timezone": "GMT",
            "start_date": "2026-10-18",
            "end_date": "2026-10-20",
        }

    def test_places_are_rounded_to_a_tenth_of_a_degree_and_deduplicated(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        route = api.get(URL).respond(200, json=fixture("single_point"))

        result = setup.provider.hourly(
            [LatLon(39.7392, -104.9903), LatLon(39.71, -105.04), LatLon(39.66, -104.96)],
            FIRST_DAY,
            LAST_DAY,
        )

        assert route.call_count == 1
        assert route.calls.last.request.url.params["latitude"] == "39.7"
        assert list(result.series) == [DENVER]

    def test_no_places_means_no_calls(self, api: respx.MockRouter, setup: Setup) -> None:
        route = api.get(URL).respond(200, json=[])

        result = setup.provider.hourly([], FIRST_DAY, LAST_DAY)

        assert dict(result.series) == {}
        assert not route.called

    def test_it_satisfies_the_weather_provider_protocol(self, setup: Setup) -> None:
        provider: WeatherProvider = setup.provider

        assert provider.name == "open-meteo"


class TestUnits:
    def with_unit(self, variable: str, unit: Any) -> dict[str, Any]:
        body: dict[str, Any] = fixture("single_point")
        if unit is None:
            del body["hourly_units"][variable]
        else:
            body["hourly_units"][variable] = unit
        return body

    @pytest.mark.parametrize(
        ("variable", "unit"),
        [
            ("wind_speed_10m", "mph"),  # what the spec wrote; the API says "mp/h"
            ("wind_speed_10m", "km/h"),
            ("wind_speed_10m", "m/s"),
            ("wind_speed_10m", "kn"),
            ("wind_gusts_10m", "km/h"),
            ("rain", "mm"),
            ("showers", "mm"),
            ("snowfall", "cm"),
            ("time", "iso8601"),
            ("rain", None),
        ],
    )
    def test_a_mismatch_is_a_contract_error_and_nothing_is_converted(
        self, api: respx.MockRouter, setup: Setup, variable: str, unit: Any
    ) -> None:
        api.get(URL).respond(200, json=self.with_unit(variable, unit))

        with pytest.raises(UpstreamContractError, match=variable):
            setup.provider.hourly([DENVER], FIRST_DAY, LAST_DAY)

    def test_a_mismatch_in_any_place_of_a_batch_fails_the_batch(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        body = fixture("four_points")
        body[3]["hourly_units"]["wind_speed_10m"] = "km/h"
        api.get(URL).respond(200, json=body)

        with pytest.raises(UpstreamContractError, match="km/h"):
            setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY)

    def test_a_mismatch_is_not_hidden_by_a_stale_cached_series(
        self, api: respx.MockRouter, setup: Setup, clock: FakeClock
    ) -> None:
        api.get(URL).respond(200, json=fixture("single_point"))
        setup.provider.hourly([DENVER], FIRST_DAY, LAST_DAY)
        clock.advance(3_600)
        api.get(URL).respond(200, json=self.with_unit("rain", "mm"))

        with pytest.raises(UpstreamContractError):
            setup.provider.hourly([DENVER], FIRST_DAY, LAST_DAY)

    def test_nothing_is_cached_from_a_rejected_response(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        api.get(URL).respond(200, json=self.with_unit("rain", "mm"))
        with pytest.raises(UpstreamContractError):
            setup.provider.hourly([DENVER], FIRST_DAY, LAST_DAY)
        route = api.get(URL).respond(200, json=fixture("single_point"))

        result = setup.provider.hourly([DENVER], FIRST_DAY, LAST_DAY)

        assert route.called
        assert result.series[DENVER] is not None


def single(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = fixture("single_point")
    for key, value in changes.items():
        if value is None:
            body["hourly"].pop(key, None)
        else:
            body["hourly"][key] = value
    return body


def with_times(times: Any) -> dict[str, Any]:
    """The recorded place with other hourly times; every column is cut to match so that only
    the times themselves can be what is wrong."""
    body = single(time=times)
    if isinstance(times, list):
        for name in HOURLY_COLUMNS:
            body["hourly"][name] = body["hourly"][name][: len(times)]
    return body


HOURLY_COLUMNS = (
    "wind_speed_10m",
    "wind_gusts_10m",
    "rain",
    "showers",
    "snowfall",
    "weather_code",
)
FIRST = fixture("single_point")["hourly"]["time"][0]
MALFORMED: dict[str, Any] = {
    "not-json-structure": "text",
    "number": 5,
    "no-units": {**fixture("single_point"), "hourly_units": None},
    "units-not-an-object": {**fixture("single_point"), "hourly_units": []},
    "no-hourly": {**fixture("single_point"), "hourly": None},
    "no-times": single(time=None),
    "empty-times": with_times([]),
    "times-not-a-list": with_times("noon"),
    "text-time": with_times(["a", "b"]),
    "float-time": with_times([float(FIRST), FIRST + 3600.0]),
    "boolean-time": with_times([True, False]),
    "off-the-hour": with_times([FIRST + 60, FIRST + 3660]),
    "gap-in-times": with_times([FIRST, FIRST + 7200, FIRST + 10800]),
    "repeated-time": with_times([FIRST, FIRST]),
    "out-of-order-times": with_times([FIRST + 3600, FIRST]),
    "wind-too-short": single(wind_speed_10m=[1.0, 2.0]),
    "gust-missing": single(wind_gusts_10m=None),
    "rain-not-a-list": single(rain="wet"),
    "text-value": single(rain=["wet"] * 72),
    "negative-wind": single(wind_speed_10m=[-1.0] * 72),
    "boolean-value": single(showers=[True] * 72),
    "code-missing": single(weather_code=None),
    "code-too-short": single(weather_code=[0]),
    "float-code": single(weather_code=[1.5] * 72),
    "boolean-code": single(weather_code=[True] * 72),
}


class TestMalformedResponses:
    @pytest.mark.parametrize("body", list(MALFORMED.values()), ids=list(MALFORMED))
    def test_unusable_bodies_are_contract_errors(
        self, api: respx.MockRouter, setup: Setup, body: Any
    ) -> None:
        api.get(URL).respond(200, json=copy.deepcopy(body))

        with pytest.raises(UpstreamContractError):
            setup.provider.hourly([DENVER], FIRST_DAY, LAST_DAY)

    def test_the_wrong_number_of_locations(self, api: respx.MockRouter, setup: Setup) -> None:
        api.get(URL).respond(200, json=fixture("four_points")[:3])

        with pytest.raises(UpstreamContractError, match="expected 4 locations"):
            setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY)

    def test_a_list_for_one_place_is_checked_too(self, api: respx.MockRouter, setup: Setup) -> None:
        api.get(URL).respond(200, json=[fixture("single_point"), fixture("single_point")])

        with pytest.raises(UpstreamContractError, match="expected 1 locations"):
            setup.provider.hourly([DENVER], FIRST_DAY, LAST_DAY)

    def test_missing_values_are_kept_as_unknown_not_rejected(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        body = single(
            wind_speed_10m=[None] + fixture("single_point")["hourly"]["wind_speed_10m"][1:],
            weather_code=[None] + fixture("single_point")["hourly"]["weather_code"][1:],
        )
        api.get(URL).respond(200, json=body)

        series = setup.provider.hourly([DENVER], FIRST_DAY, LAST_DAY).series[DENVER]

        assert series is not None
        assert series.wind_mph[0] is None
        assert series.weather_code[0] is None
        assert series.wind_mph[1] is not None

    def test_a_rejected_request_is_not_an_outage(self, api: respx.MockRouter, setup: Setup) -> None:
        api.get(URL).respond(400, json=fixture("bad_request"))

        with pytest.raises(UpstreamError) as raised:
            setup.provider.hourly([DENVER], FIRST_DAY, LAST_DAY)

        assert type(raised.value) is UpstreamError
        assert raised.value.status == 400

    def test_invalid_day_ranges_are_refused(self, setup: Setup) -> None:
        with pytest.raises(ValueError, match="before"):
            setup.provider.hourly([DENVER], LAST_DAY, FIRST_DAY)
        with pytest.raises(ValueError, match="at most 16 days"):
            setup.provider.hourly([DENVER], FIRST_DAY, FIRST_DAY + timedelta(days=16))

    def test_sixteen_days_are_allowed(self, api: respx.MockRouter, setup: Setup) -> None:
        api.get(URL).respond(200, json=fixture("single_point"))

        setup.provider.hourly([DENVER], FIRST_DAY, FIRST_DAY + timedelta(days=15))


class TestBatching:
    def test_250_places_make_three_calls_of_100_100_and_50(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        replier = Replier()
        api.get(URL).mock(side_effect=replier)

        result = setup.provider.hourly(grid(250), FIRST_DAY, LAST_DAY)

        assert sorted(replier.sizes) == [50, 100, 100]
        assert len(result.series) == 250
        assert result.missing == 0

    def test_100_places_make_one_call_and_101_make_two(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        replier = Replier()
        api.get(URL).mock(side_effect=replier)

        setup.provider.hourly(grid(100), FIRST_DAY, LAST_DAY)
        assert replier.sizes == [100]
        setup.backend.clear()
        replier.sizes.clear()
        setup.provider.hourly(grid(101), FIRST_DAY, LAST_DAY)

        assert sorted(replier.sizes) == [1, 100]

    def test_at_most_four_batches_are_in_flight_at_once(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        replier = Replier(delay_s=0.05)
        api.get(URL).mock(side_effect=replier)

        setup.provider.hourly(grid(800), FIRST_DAY, LAST_DAY)  # eight batches

        assert len(replier.sizes) == 8
        assert 2 <= replier.max_in_flight <= 4

    def test_the_adapters_own_limit_holds_even_if_the_client_would_allow_more(
        self, api: respx.MockRouter, clock: FakeClock
    ) -> None:
        setup = Setup(clock, client_concurrency=20)
        replier = Replier(delay_s=0.05)
        api.get(URL).mock(side_effect=replier)

        setup.provider.hourly(grid(1200), FIRST_DAY, LAST_DAY)  # twelve batches

        assert len(replier.sizes) == 12
        assert 2 <= replier.max_in_flight <= 4
        setup.close()

    def test_every_place_is_matched_with_its_own_batch_position(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        template = fixture("single_point")

        def reply(request: httpx.Request) -> httpx.Response:
            latitudes = [float(value) for value in request.url.params["latitude"].split(",")]
            places = []
            for latitude in latitudes:
                place = copy.deepcopy(template)
                place["hourly"]["wind_speed_10m"] = [latitude] * 72  # marks the place
                places.append(place)
            return httpx.Response(200, json=places)

        api.get(URL).mock(side_effect=reply)
        points = [LatLon(20.0 + step * 0.1, -100.0) for step in range(230)]

        result = setup.provider.hourly(points, FIRST_DAY, LAST_DAY)

        for point in points:
            series = result.series[rounded_point(point)]
            assert series is not None
            assert series.wind_mph[0] == pytest.approx(rounded_point(point).lat)


class TestCache:
    def test_a_second_request_for_the_same_places_makes_no_call(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        route = api.get(URL).respond(200, json=fixture("four_points"))
        first = setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY)

        second = setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY)

        assert route.call_count == 1
        assert second.series == first.series
        assert (second.stale, second.missing) == (False, 0)

    def test_only_the_places_not_cached_are_requested(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        replier = Replier()
        route = api.get(URL).mock(side_effect=replier)
        setup.provider.hourly([SEATTLE, RAINIER], FIRST_DAY, LAST_DAY)

        result = setup.provider.hourly([SEATTLE, RAINIER, LOVELAND], FIRST_DAY, LAST_DAY)

        assert route.call_count == 2
        assert replier.requests[-1].url.params["latitude"] == "39.7"
        assert len(result.series) == 3

    def test_cached_places_include_those_that_round_to_the_same_cell(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        route = api.get(URL).respond(200, json=fixture("single_point"))
        setup.provider.hourly([DENVER], FIRST_DAY, LAST_DAY)

        setup.provider.hourly([LatLon(39.74, -104.96)], FIRST_DAY, LAST_DAY)

        assert route.call_count == 1

    def test_a_different_day_range_is_a_different_request(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        route = api.get(URL).respond(200, json=fixture("single_point"))
        setup.provider.hourly([DENVER], FIRST_DAY, LAST_DAY)

        setup.provider.hourly([DENVER], FIRST_DAY, FIRST_DAY)

        assert route.call_count == 2

    def test_a_series_is_fresh_for_thirty_minutes(
        self, api: respx.MockRouter, setup: Setup, clock: FakeClock
    ) -> None:
        route = api.get(URL).respond(200, json=fixture("single_point"))
        setup.provider.hourly([DENVER], FIRST_DAY, LAST_DAY)

        clock.advance(30 * 60 - 1)
        setup.provider.hourly([DENVER], FIRST_DAY, LAST_DAY)
        assert route.call_count == 1

        clock.advance(1)
        setup.provider.hourly([DENVER], FIRST_DAY, LAST_DAY)
        assert route.call_count == 2


class TestOutages:
    def warm_up(self, api: respx.MockRouter, setup: Setup) -> None:
        api.get(URL).respond(200, json=fixture("four_points"))
        setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY)

    def test_stale_series_are_served_and_flagged_when_open_meteo_is_down(
        self, api: respx.MockRouter, setup: Setup, clock: FakeClock
    ) -> None:
        self.warm_up(api, setup)
        clock.advance(2 * 3600)
        api.get(URL).respond(503)

        result = setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY)

        assert result.stale is True
        assert result.missing == 0
        assert all(isinstance(series, HourlySeries) for series in result.series.values())

    def test_stale_series_are_the_ones_that_were_cached(
        self, api: respx.MockRouter, setup: Setup, clock: FakeClock
    ) -> None:
        self.warm_up(api, setup)
        before = setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY).series
        clock.advance(2 * 3600)
        api.get(URL).mock(side_effect=httpx.ReadTimeout("slow"))

        after = setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY)

        assert after.series == before
        assert after.stale is True

    def test_after_six_hours_the_places_come_back_without_weather(
        self, api: respx.MockRouter, setup: Setup, clock: FakeClock
    ) -> None:
        self.warm_up(api, setup)
        clock.advance(6 * 3600)
        api.get(URL).respond(503)

        result = setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY)

        assert result.series == dict.fromkeys(FOUR_PLACES)
        assert (result.stale, result.missing) == (False, 4)

    def test_just_inside_six_hours_the_stale_series_still_serve(
        self, api: respx.MockRouter, setup: Setup, clock: FakeClock
    ) -> None:
        self.warm_up(api, setup)
        clock.advance(6 * 3600 - 1)
        api.get(URL).respond(503)

        result = setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY)

        assert (result.stale, result.missing) == (True, 0)

    def test_an_outage_with_nothing_cached_degrades_instead_of_failing(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        api.get(URL).respond(503)

        result = setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY)

        assert result.series == dict.fromkeys(FOUR_PLACES)
        assert (result.stale, result.missing) == (False, 4)

    def test_a_timeout_degrades_too(self, api: respx.MockRouter, setup: Setup) -> None:
        api.get(URL).mock(side_effect=httpx.ReadTimeout("slow"))

        result = setup.provider.hourly([DENVER], FIRST_DAY, LAST_DAY)

        assert result.missing == 1

    def test_one_failed_batch_does_not_lose_the_others(
        self, api: respx.MockRouter, setup: Setup
    ) -> None:
        template = fixture("single_point")

        def reply(request: httpx.Request) -> httpx.Response:
            latitudes = request.url.params["latitude"].split(",")
            if len(latitudes) == 50:
                return httpx.Response(503)
            return httpx.Response(200, json=[copy.deepcopy(template) for _ in latitudes])

        api.get(URL).mock(side_effect=reply)

        result = setup.provider.hourly(grid(250), FIRST_DAY, LAST_DAY)

        assert result.missing == 50
        assert sum(series is not None for series in result.series.values()) == 200

    def test_recovery_after_an_outage_gives_fresh_series_again(
        self, api: respx.MockRouter, setup: Setup, clock: FakeClock
    ) -> None:
        self.warm_up(api, setup)
        clock.advance(2 * 3600)
        api.get(URL).respond(503)
        assert setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY).stale is True
        clock.advance(120)  # past the breaker's reset time
        api.get(URL).respond(200, json=fixture("four_points"))

        result = setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY)

        assert (result.stale, result.missing) == (False, 0)

    def test_an_exhausted_request_deadline_degrades_to_missing_weather(
        self, api: respx.MockRouter, setup: Setup, clock: FakeClock
    ) -> None:
        route = api.get(URL).respond(200, json=fixture("four_points"))

        with deadline_scope(5.0, clock):
            clock.advance(6.0)
            result = setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY)

        assert not route.called
        assert result.missing == 4

    def test_the_deadline_reaches_the_worker_threads(
        self, api: respx.MockRouter, setup: Setup, clock: FakeClock
    ) -> None:
        route = api.get(URL).respond(200, json=fixture("four_points"))

        with deadline_scope(20.0, clock):
            clock.advance(17.0)
            setup.provider.hourly(FOUR_PLACES, FIRST_DAY, LAST_DAY)

        assert route.calls.last.request.extensions["timeout"]["read"] == pytest.approx(3.0)


class TestRoundedPoint:
    @pytest.mark.parametrize(
        ("point", "expected"),
        [
            (LatLon(39.7392, -104.9903), LatLon(39.7, -105.0)),
            (LatLon(39.76, -104.94), LatLon(39.8, -104.9)),
            (LatLon(-33.86, 151.21), LatLon(-33.9, 151.2)),
            (LatLon(-0.04, 0.04), LatLon(0.0, 0.0)),
        ],
    )
    def test_rounds_to_a_tenth_of_a_degree(self, point: LatLon, expected: LatLon) -> None:
        assert rounded_point(point) == expected

    def test_lattice_points_are_unchanged(self) -> None:
        assert rounded_point(LatLon(40.4, -105.2)) == LatLon(40.4, -105.2)
