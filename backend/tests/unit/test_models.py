import dataclasses
from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from planner.domain.models import (
    Checkpoint,
    HourlySeries,
    LatLon,
    RiskLevel,
    RouteScore,
    Stretch,
    WeatherSample,
    combine_levels,
    is_known,
    max_known,
)

KNOWN_LEVELS = [
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.SEVERE,
    RiskLevel.NO_TRAVEL,
]


class TestRiskLevel:
    def test_known_levels_are_ordered_from_low_to_no_travel(self) -> None:
        assert sorted(KNOWN_LEVELS) == KNOWN_LEVELS
        assert [int(level) for level in KNOWN_LEVELS] == [0, 1, 2, 3, 4]

    @pytest.mark.parametrize(
        ("lower", "higher"),
        [
            (RiskLevel.LOW, RiskLevel.MODERATE),
            (RiskLevel.MODERATE, RiskLevel.HIGH),
            (RiskLevel.HIGH, RiskLevel.SEVERE),
            (RiskLevel.SEVERE, RiskLevel.NO_TRAVEL),
        ],
    )
    def test_each_level_ranks_below_the_next(self, lower: RiskLevel, higher: RiskLevel) -> None:
        assert lower < higher

    def test_unknown_uses_the_wire_value_minus_one(self) -> None:
        assert int(RiskLevel.UNKNOWN) == -1


class TestIsKnown:
    @pytest.mark.parametrize("level", KNOWN_LEVELS)
    def test_real_levels_are_known(self, level: RiskLevel) -> None:
        assert is_known(level)

    def test_unknown_is_not_known(self) -> None:
        assert not is_known(RiskLevel.UNKNOWN)


class TestMaxKnown:
    def test_returns_highest_level(self) -> None:
        assert max_known([RiskLevel.LOW, RiskLevel.HIGH, RiskLevel.MODERATE]) is RiskLevel.HIGH

    def test_ignores_unknown_among_known_levels(self) -> None:
        assert max_known([RiskLevel.UNKNOWN, RiskLevel.LOW]) is RiskLevel.LOW

    def test_unknown_is_never_reported_as_low(self) -> None:
        assert max_known([RiskLevel.UNKNOWN, RiskLevel.UNKNOWN]) is RiskLevel.UNKNOWN

    def test_empty_input_is_unknown(self) -> None:
        assert max_known([]) is RiskLevel.UNKNOWN

    def test_accepts_any_iterable(self) -> None:
        assert max_known(level for level in KNOWN_LEVELS) is RiskLevel.NO_TRAVEL

    @given(st.lists(st.sampled_from([*KNOWN_LEVELS, RiskLevel.UNKNOWN])))
    def test_equals_maximum_of_known_levels(self, levels: list[RiskLevel]) -> None:
        known = [level for level in levels if level is not RiskLevel.UNKNOWN]
        expected = max(known) if known else RiskLevel.UNKNOWN
        assert max_known(levels) is expected


class TestCombineLevels:
    def test_known_levels_combine_to_the_worst(self) -> None:
        assert combine_levels([RiskLevel.LOW, RiskLevel.HIGH]) is RiskLevel.HIGH

    @pytest.mark.parametrize("known", [RiskLevel.LOW, RiskLevel.MODERATE, RiskLevel.HIGH])
    def test_unknown_with_a_milder_level_is_unknown(self, known: RiskLevel) -> None:
        assert combine_levels([known, RiskLevel.UNKNOWN]) is RiskLevel.UNKNOWN

    @pytest.mark.parametrize("known", [RiskLevel.SEVERE, RiskLevel.NO_TRAVEL])
    def test_unknown_does_not_hide_known_danger(self, known: RiskLevel) -> None:
        assert combine_levels([RiskLevel.UNKNOWN, known]) is known

    def test_all_unknown_and_empty_are_unknown(self) -> None:
        assert combine_levels([RiskLevel.UNKNOWN, RiskLevel.UNKNOWN]) is RiskLevel.UNKNOWN
        assert combine_levels([]) is RiskLevel.UNKNOWN

    def test_order_does_not_matter(self) -> None:
        assert combine_levels([RiskLevel.SEVERE, RiskLevel.UNKNOWN]) is RiskLevel.SEVERE
        assert combine_levels([RiskLevel.UNKNOWN, RiskLevel.SEVERE]) is RiskLevel.SEVERE


class TestLatLon:
    @pytest.mark.parametrize(
        ("lat", "lon"),
        [(0.0, 0.0), (39.7392, -104.9903), (90.0, 180.0), (-90.0, -180.0)],
    )
    def test_accepts_valid_coordinates(self, lat: float, lon: float) -> None:
        point = LatLon(lat, lon)

        assert (point.lat, point.lon) == (lat, lon)

    @pytest.mark.parametrize(
        ("lat", "lon"),
        [(90.0001, 0.0), (-90.0001, 0.0), (0.0, 180.0001), (0.0, -180.0001)],
    )
    def test_rejects_out_of_range_coordinates(self, lat: float, lon: float) -> None:
        with pytest.raises(ValueError, match="outside"):
            LatLon(lat, lon)

    def test_is_immutable(self) -> None:
        point = LatLon(1.0, 2.0)

        with pytest.raises(dataclasses.FrozenInstanceError):
            point.lat = 3.0  # type: ignore[misc]

    def test_equal_coordinates_compare_equal(self) -> None:
        assert LatLon(1.0, 2.0) == LatLon(1.0, 2.0)


class TestWeatherSample:
    def test_defaults_to_all_values_unavailable(self) -> None:
        sample = WeatherSample()

        assert sample == WeatherSample(None, None, None, None, None)


class TestCheckpoint:
    def test_defaults_to_unknown_level_without_weather(self) -> None:
        checkpoint = Checkpoint(
            index=0,
            location=LatLon(40.0, -105.0),
            distance_mi=0.0,
            eta=datetime(2026, 1, 1, 12, tzinfo=UTC),
        )

        assert checkpoint.level is RiskLevel.UNKNOWN
        assert checkpoint.weather is None
        assert checkpoint.reasons == ()

    def test_rejects_naive_eta(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            Checkpoint(
                index=0,
                location=LatLon(40.0, -105.0),
                distance_mi=0.0,
                eta=datetime(2026, 1, 1, 12),  # noqa: DTZ001 - the naive value is the test input
            )

    def test_is_immutable(self) -> None:
        checkpoint = Checkpoint(0, LatLon(40.0, -105.0), 0.0, datetime(2026, 1, 1, tzinfo=UTC))

        with pytest.raises(dataclasses.FrozenInstanceError):
            checkpoint.level = RiskLevel.LOW  # type: ignore[misc]


class TestStretchAndRouteScore:
    def test_stretch_holds_its_values(self) -> None:
        stretch = Stretch(start_index=0, end_index=1, length_mi=25.0, level=RiskLevel.HIGH)

        assert (stretch.start_index, stretch.end_index) == (0, 1)
        assert stretch.length_mi == 25.0
        assert stretch.level is RiskLevel.HIGH

    def test_route_score_defaults_do_not_claim_any_risk_level(self) -> None:
        score = RouteScore(distance_mi=100.0, duration_s=6000.0)

        assert score.miles_by_level == {}
        assert score.unknown_miles == 0.0
        assert score.avg_risk is None
        assert score.worst_level is RiskLevel.UNKNOWN
        assert not score.low_confidence

    def test_route_score_default_mappings_are_not_shared(self) -> None:
        first = RouteScore(distance_mi=1.0, duration_s=1.0)
        second = RouteScore(distance_mi=1.0, duration_s=1.0)

        assert first.miles_by_level is not second.miles_by_level


class TestHourlySeries:
    START = datetime(2026, 1, 15, 12, tzinfo=UTC)

    def build(self, start: datetime | None = None, length: int = 3) -> HourlySeries:
        values = (0.0,) * length
        return HourlySeries(
            start=start or self.START,
            wind_mph=values,
            gust_mph=values,
            rain_in=values,
            showers_in=values,
            snowfall_in=values,
            weather_code=(0,) * length,
        )

    def test_reports_its_length_and_last_entry_time(self) -> None:
        series = self.build(length=4)

        assert len(series) == 4
        assert series.end == datetime(2026, 1, 15, 15, tzinfo=UTC)

    def test_rejects_a_naive_start(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            self.build(start=datetime(2026, 1, 15, 12))  # noqa: DTZ001 - the naive value is the input

    def test_rejects_a_start_that_is_not_on_the_hour(self) -> None:
        with pytest.raises(ValueError, match="on the hour"):
            self.build(start=datetime(2026, 1, 15, 12, 30, tzinfo=UTC))

    def test_rejects_series_of_different_lengths(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            HourlySeries(
                start=self.START,
                wind_mph=(1.0, 2.0),
                gust_mph=(1.0,),
                rain_in=(0.0, 0.0),
                showers_in=(0.0, 0.0),
                snowfall_in=(0.0, 0.0),
                weather_code=(0, 0),
            )
