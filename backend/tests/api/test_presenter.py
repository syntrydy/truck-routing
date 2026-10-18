import gzip
import json
import random
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import pytest

from planner.api.presenters import present_plan
from planner.api.serializers import PlanResponseSerializer
from planner.domain.geometry import destination_point, distance_to_polyline_m
from planner.domain.models import HourlySeries, LatLon
from planner.domain.risk import WindBasis
from planner.providers.protocols import WeatherResult, rounded_point
from planner.services.models import PlanRequest, PlanResult
from planner.services.plan import PlanService
from tests.infra.fakes import FakeClock
from tests.services.stubs import START, StubRouting, StubWeather, route

DEPARTURE = datetime(2026, 10, 18, 14, 0, tzinfo=UTC)
NOW = datetime(2026, 10, 18, 13, 55, 21, 987654, tzinfo=UTC)


def plan(
    routes: list[Any],
    weather: StubWeather | None = None,
    **changes: Any,
) -> PlanResult:
    service = PlanService(
        StubRouting(routes),
        weather or StubWeather(),
        max_speed_mph=65.0,
        wind_basis=WindBasis.SUSTAINED,
        now=lambda: NOW,
        monotonic=FakeClock(),
    )
    request = PlanRequest(
        origin=routes[0].points[0],
        destination=routes[0].points[-1],
        departure=DEPARTURE,
        load_lb=changes.get("load_lb", 20_000),
        interval_mi=changes.get("interval_mi", 25),
    )
    return service.plan(request)


def three_routes(step_m: float = 5_000.0, length_mi: float = 60.0) -> list[Any]:
    return [
        route(length_mi, 55, step_m=step_m),
        route(length_mi + 2, 52, origin=destination_point(START, 0.0, 20_000), step_m=step_m),
        route(length_mi + 5, 50, origin=destination_point(START, 180.0, 20_000), step_m=step_m),
    ]


@pytest.fixture(scope="module")
def result() -> PlanResult:
    return plan(three_routes(step_m=500.0))


@pytest.fixture(scope="module")
def body(result: PlanResult) -> dict[str, Any]:
    return present_plan(result, "req-123")


class TestShape:
    def test_the_top_level_keys_follow_the_spec(self, body: dict[str, Any]) -> None:
        assert list(body) == [
            "recommended_route_id",
            "recommendation_reason",
            "banner",
            "routes",
            "heatmap",
            "notes",
            "meta",
        ]

    def test_a_route_has_the_documented_keys(self, body: dict[str, Any]) -> None:
        route_body = body["routes"][0]

        assert list(route_body) == [
            "id",
            "label",
            "rank",
            "distance_mi",
            "duration_s",
            "geometry",
            "summary",
            "checkpoints",
        ]
        assert list(route_body["summary"]) == [
            "miles_by_level",
            "unknown_miles",
            "avg_risk",
            "worst_level",
            "low_confidence",
        ]
        assert list(route_body["summary"]["miles_by_level"]) == [
            "LOW",
            "MODERATE",
            "HIGH",
            "SEVERE",
            "NO_TRAVEL",
        ]

    def test_a_checkpoint_has_the_documented_keys(self, body: dict[str, Any]) -> None:
        assert list(body["routes"][0]["checkpoints"][0]) == [
            "index",
            "mile",
            "lat",
            "lon",
            "eta",
            "wind_mph",
            "gust_mph",
            "rain_in_hr",
            "snow_in_hr",
            "level",
            "reasons",
        ]

    def test_the_heatmap_and_meta_have_the_documented_keys(self, body: dict[str, Any]) -> None:
        assert list(body["heatmap"]) == ["start", "points", "frames"]
        assert list(body["heatmap"]["frames"][0]) == ["risk", "wind", "rain", "snow"]
        assert list(body["meta"]) == [
            "routing_source",
            "weather_source",
            "weather_stale",
            "generated_at",
            "request_id",
        ]

    def test_the_output_is_plain_json(self, body: dict[str, Any]) -> None:
        assert json.loads(json.dumps(body)) == body

    def test_the_output_matches_the_schema_serializer(self, body: dict[str, Any]) -> None:
        serializer = PlanResponseSerializer(data=body)

        assert serializer.is_valid(), serializer.errors

    def test_the_output_matches_the_schema_when_weather_is_missing(self) -> None:
        missing = present_plan(plan(three_routes(), StubWeather(lambda place: None)), "r")
        serializer = PlanResponseSerializer(data=missing)

        assert serializer.is_valid(), serializer.errors
        assert missing["banner"] == "WEATHER_UNAVAILABLE"

    def test_the_output_matches_the_schema_when_there_is_no_safe_route(self) -> None:
        stormy = present_plan(plan(three_routes(), StubWeather(lambda place: {"wind": 60.0})), "r")
        serializer = PlanResponseSerializer(data=stormy)

        assert serializer.is_valid(), serializer.errors
        assert stormy["banner"] == "NO_SAFE_ROUTE"
        assert stormy["recommended_route_id"] is None


class TestValues:
    def test_the_recommendation_and_the_rank_agree(self, body: dict[str, Any]) -> None:
        assert body["recommended_route_id"] == body["routes"][0]["id"]
        assert [r["rank"] for r in body["routes"]] == [1, 2, 3]
        assert isinstance(body["recommendation_reason"], str)

    def test_the_meta_names_the_sources_and_the_request(self, body: dict[str, Any]) -> None:
        assert body["meta"] == {
            "routing_source": "osrm",
            "weather_source": "stub-weather",
            "weather_stale": False,
            "generated_at": "2026-10-18T13:55:21Z",
            "request_id": "req-123",
        }

    def test_times_are_utc_with_a_z_and_whole_seconds(self, body: dict[str, Any]) -> None:
        first = body["routes"][0]["checkpoints"][0]

        assert first["eta"] == "2026-10-18T14:00:00Z"
        assert body["heatmap"]["start"] == "2026-10-18T14:00:00Z"

    def test_a_time_with_another_offset_is_written_in_utc(self) -> None:
        local = DEPARTURE.astimezone(timezone(timedelta(hours=-6)))
        service = PlanService(
            StubRouting(three_routes()),
            StubWeather(),
            max_speed_mph=65.0,
            wind_basis=WindBasis.SUSTAINED,
            now=lambda: NOW.astimezone(timezone(timedelta(hours=9))),
            monotonic=FakeClock(),
        )
        routes = three_routes()

        output = present_plan(
            service.plan(PlanRequest(routes[0].points[0], routes[0].points[-1], local, 20_000, 25)),
            "r",
        )

        assert output["meta"]["generated_at"] == "2026-10-18T13:55:21Z"
        assert output["routes"][0]["checkpoints"][0]["eta"] == "2026-10-18T14:00:00Z"

    def test_a_banner_is_its_name_and_none_is_null(self, body: dict[str, Any]) -> None:
        assert body["banner"] is None

    def test_the_geometry_is_geojson_with_longitude_first(self, body: dict[str, Any]) -> None:
        geometry = body["routes"][0]["geometry"]

        assert geometry["type"] == "LineString"
        lon, lat = geometry["coordinates"][0]
        assert lon == pytest.approx(START.lon, abs=1e-4)
        assert lat == pytest.approx(START.lat, abs=1e-4)

    def test_heatmap_points_are_latitude_first(self, body: dict[str, Any]) -> None:
        lat, lon = body["heatmap"]["points"][0]

        assert 30 < lat < 50
        assert -120 < lon < -90

    def test_checkpoint_levels_and_reasons_are_names_and_texts(self) -> None:
        stormy = present_plan(plan(three_routes(), StubWeather(lambda place: {"wind": 50.0})), "r")

        checkpoint = stormy["routes"][0]["checkpoints"][1]

        assert checkpoint["level"] == "SEVERE"
        assert checkpoint["reasons"] == ["Wind 50 mph → Severe"]

    def test_missing_weather_is_null_and_the_level_unknown(self) -> None:
        missing = present_plan(plan(three_routes(), StubWeather(lambda place: None)), "r")

        checkpoint = missing["routes"][0]["checkpoints"][0]
        assert checkpoint["level"] == "UNKNOWN"
        assert checkpoint["wind_mph"] is None
        assert checkpoint["rain_in_hr"] is None
        assert missing["routes"][0]["summary"]["avg_risk"] is None
        assert missing["routes"][0]["summary"]["worst_level"] == "UNKNOWN"
        assert set(missing["heatmap"]["frames"][0]["wind"]) == {None}
        assert set(missing["heatmap"]["frames"][0]["risk"]) == {-1}

    def test_the_heatmap_has_49_frames_with_one_value_per_point(self, body: dict[str, Any]) -> None:
        heatmap = body["heatmap"]

        assert len(heatmap["frames"]) == 49
        for frame in heatmap["frames"]:
            assert all(len(values) == len(heatmap["points"]) for values in frame.values())


class TestCompaction:
    def test_the_route_line_is_simplified_but_keeps_its_ends(self) -> None:
        routes = three_routes(step_m=100.0)  # a vertex every 100 m
        output = present_plan(plan(routes), "r")

        line = output["routes"][0]["geometry"]["coordinates"]

        assert len(routes[0].points) > 900
        assert len(line) <= 5  # a nearly straight road needs only a few points
        assert line[0] == [round(routes[0].points[0].lon, 5), round(routes[0].points[0].lat, 5)]
        assert line[-1] == [round(routes[0].points[-1].lon, 5), round(routes[0].points[-1].lat, 5)]

    def test_the_simplified_line_stays_within_the_tolerance_of_the_original(self) -> None:
        routes = three_routes(step_m=100.0)
        output = present_plan(plan(routes), "r")
        simplified = [
            LatLon(lat, lon) for lon, lat in output["routes"][0]["geometry"]["coordinates"]
        ]

        farthest = max(
            distance_to_polyline_m(point, simplified) for point in routes[0].points[::10]
        )

        assert farthest <= 55.0  # 50 m, plus a little for the 5-decimal rounding

    def test_a_bend_larger_than_the_tolerance_is_kept(self) -> None:
        main = route(60, 55)
        corner = destination_point(START, 90.0, 40_000)
        bent_points = (
            *[destination_point(START, 90.0, 4_000 * i) for i in range(11)],
            *[destination_point(corner, 0.0, 4_000 * i) for i in range(1, 11)],
        )
        bent = type(main)(
            points=bent_points,
            distance_m=main.distance_m,
            duration_s=main.duration_s,
            segment_durations_s=tuple(main.duration_s / 20 for _ in range(20)),
            segment_distances_m=tuple(main.distance_m / 20 for _ in range(20)),
        )

        output = present_plan(plan([bent, *three_routes()[1:]]), "r")

        match = min(output["routes"], key=lambda r: abs(r["distance_mi"] - 49.7))
        assert len(match["geometry"]["coordinates"]) >= 3

    def test_coordinates_are_rounded_to_five_decimals(self, body: dict[str, Any]) -> None:
        for lon, lat in body["routes"][0]["geometry"]["coordinates"]:
            assert round(lon, 5) == lon
            assert round(lat, 5) == lat

    def test_numbers_are_rounded(self, body: dict[str, Any]) -> None:
        first = body["routes"][0]
        checkpoint = first["checkpoints"][1]

        assert round(first["distance_mi"], 1) == first["distance_mi"]
        assert isinstance(first["duration_s"], int)
        assert round(checkpoint["mile"], 1) == checkpoint["mile"]
        assert round(checkpoint["lat"], 4) == checkpoint["lat"]
        assert round(checkpoint["wind_mph"], 1) == checkpoint["wind_mph"]
        assert round(checkpoint["rain_in_hr"], 3) == checkpoint["rain_in_hr"]
        for lat, lon in body["heatmap"]["points"]:
            assert round(lat, 4) == lat
            assert round(lon, 4) == lon

    def test_every_number_is_the_rounded_original_not_just_short(self) -> None:
        odd = plan(three_routes(length_mi=60.37))
        output = present_plan(odd, "r")

        for original, shown in zip(odd.routes, output["routes"], strict=True):
            assert shown["distance_mi"] == round(original.distance_mi, 1)
            assert shown["duration_s"] == round(original.duration_s)
            for cp, shown_cp in zip(original.checkpoints, shown["checkpoints"], strict=True):
                assert shown_cp["mile"] == round(cp.distance_mi, 1)
                assert shown_cp["lat"] == round(cp.location.lat, 4)
                assert shown_cp["lon"] == round(cp.location.lon, 4)

    def test_the_rounding_is_finer_than_the_coarser_alternatives(self) -> None:
        odd = plan(three_routes(length_mi=60.37))
        output = present_plan(odd, "r")
        pairs = [
            (cp, shown_cp)
            for original, shown in zip(odd.routes, output["routes"], strict=True)
            for cp, shown_cp in zip(original.checkpoints, shown["checkpoints"], strict=True)
        ]

        assert any(shown["lat"] != round(cp.location.lat, 3) for cp, shown in pairs)
        assert any(shown["mile"] != round(cp.distance_mi, 0) for cp, shown in pairs)
        assert any(shown["mile"] != round(cp.distance_mi, 2) for cp, shown in pairs)

    def test_the_average_risk_keeps_two_decimals(self) -> None:
        mixed = plan(
            three_routes(), StubWeather(lambda place: {"wind": 30.0} if place.lon < -104.8 else {})
        )
        output = present_plan(mixed, "r")

        for original, shown in zip(mixed.routes, output["routes"], strict=True):
            average = original.score.avg_risk
            assert average is not None
            assert shown["summary"]["avg_risk"] == round(average, 2)
        assert any(
            r["summary"]["avg_risk"] != round(r["summary"]["avg_risk"], 1) for r in output["routes"]
        )

    def test_unknown_miles_are_reported(self) -> None:
        missing = plan(three_routes(), StubWeather(lambda place: None))
        output = present_plan(missing, "r")

        assert output["routes"][0]["summary"]["unknown_miles"] == round(
            missing.routes[0].score.unknown_miles, 1
        )
        assert output["routes"][0]["summary"]["unknown_miles"] > 50

    def test_a_checkpoint_without_weather_has_null_readings(self, result: PlanResult) -> None:
        first = result.routes[0]
        bare = replace(first, checkpoints=(replace(first.checkpoints[0], weather=None),))

        output = present_plan(replace(result, routes=(bare,)), "r")

        checkpoint = output["routes"][0]["checkpoints"][0]
        assert (checkpoint["wind_mph"], checkpoint["gust_mph"]) == (None, None)
        assert (checkpoint["rain_in_hr"], checkpoint["snow_in_hr"]) == (None, None)

    def test_the_banner_is_a_plain_string(self) -> None:
        stormy = present_plan(plan(three_routes(), StubWeather(lambda place: {"wind": 60.0})), "r")

        assert type(stormy["banner"]) is str

    def test_rounding_values(self) -> None:
        weather = StubWeather(lambda place: {"wind": 12.3456, "rain": 0.123456, "snow": 0.0004})
        output = present_plan(plan(three_routes(), weather), "r")

        checkpoint = output["routes"][0]["checkpoints"][0]

        assert checkpoint["wind_mph"] == 12.3
        assert checkpoint["rain_in_hr"] == 0.123
        assert checkpoint["snow_in_hr"] == 0.0
        assert output["heatmap"]["frames"][0]["wind"][0] == 12.3
        assert output["heatmap"]["frames"][0]["rain"][0] == 0.123


class NoisyWeather(StubWeather):
    """Weather that differs by place and by hour, as a real forecast does (not compressible)."""

    def hourly(self, points, first_day: date, last_day: date) -> WeatherResult:  # type: ignore[no-untyped-def]  # noqa: ANN001
        hours = ((last_day - first_day).days + 1) * 24
        start = datetime(first_day.year, first_day.month, first_day.day, tzinfo=UTC)
        series: dict[LatLon, HourlySeries | None] = {}
        for place in dict.fromkeys(rounded_point(p) for p in points):
            rng = random.Random(f"{place.lat:.1f},{place.lon:.1f}")  # noqa: S311 - test data
            wind = [round(rng.uniform(0, 30), 1) for _ in range(hours)]
            series[place] = HourlySeries(
                start=start,
                wind_mph=tuple(wind),
                gust_mph=tuple(round(value * rng.uniform(1.1, 1.6), 1) for value in wind),
                rain_in=tuple(
                    round(rng.uniform(0, 0.4), 3) if rng.random() < 0.15 else 0.0
                    for _ in range(hours)
                ),
                showers_in=(0.0,) * hours,
                snowfall_in=tuple(
                    round(rng.uniform(0, 0.6), 3) if rng.random() < 0.05 else 0.0
                    for _ in range(hours)
                ),
                weather_code=(0,) * hours,
            )
        self.calls.append((list(points), first_day, last_day))
        return WeatherResult(series=series, source="stub-weather")


class TestPayloadSize:
    def test_a_thousand_mile_trip_stays_under_300_kb_gzipped(self) -> None:
        # Three real-world-sized route lines: a vertex every 80 m is about 20,000 per route.
        routes = [
            route(1_000, 55, step_m=80.0),
            route(1_020, 52, origin=destination_point(START, 0.0, 40_000), step_m=80.0),
            route(1_050, 50, origin=destination_point(START, 180.0, 40_000), step_m=80.0),
        ]
        assert all(len(r.points) > 15_000 for r in routes)
        output = present_plan(plan(routes, NoisyWeather(), interval_mi=10), "r")

        raw = json.dumps(output, separators=(",", ":")).encode()
        compressed = gzip.compress(raw)

        assert len(compressed) <= 300 * 1024
        assert len(output["heatmap"]["frames"]) == 49
        assert len(output["heatmap"]["points"]) > 100
        assert len(output["routes"]) == 3
        assert all(len(r["geometry"]["coordinates"]) < 100 for r in output["routes"])
