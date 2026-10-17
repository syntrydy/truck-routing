from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from planner.domain.models import HourlySeries, RiskLevel, WeatherSample
from planner.domain.risk import classify_rain
from planner.domain.weather_select import select_weather

START = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
HOURS = 6  # entries for 12:00 .. 17:00


def at(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return START.replace(hour=hour, minute=minute, second=second)


def series(**overrides: tuple[float | None, ...] | tuple[int | None, ...]) -> HourlySeries:
    """Six hours from 12:00 with distinct values per hour so the chosen hour is visible."""
    values: dict[str, tuple[float | None, ...] | tuple[int | None, ...]] = {
        "wind_mph": (10.0, 20.0, 30.0, 40.0, 50.0, 60.0),
        "gust_mph": (15.0, 25.0, 35.0, 45.0, 55.0, 65.0),
        "rain_in": (0.00, 0.10, 0.20, 0.30, 0.40, 0.50),
        "showers_in": (0.00, 0.01, 0.02, 0.03, 0.04, 0.05),
        "snowfall_in": (0.0, 1.0, 2.0, 3.0, 4.0, 5.0),
        "weather_code": (0, 1, 2, 3, 4, 5),
    }
    values.update(overrides)
    return HourlySeries(start=START, **values)  # type: ignore[arg-type]


class TestHourSelection:
    def test_eta_on_the_hour_uses_that_hours_values(self) -> None:
        sample = select_weather(series(), at(14))

        assert sample == WeatherSample(
            wind_mph=30.0, gust_mph=35.0, rain_in_hr=0.22, snow_in_hr=2.0, weather_code=2
        )

    def test_precipitation_comes_from_the_following_hour_mark(self) -> None:
        sample = select_weather(series(), at(14, 20))

        assert sample.rain_in_hr == pytest.approx(0.33)  # 15:00: 0.30 + 0.03
        assert sample.snow_in_hr == 3.0
        assert sample.weather_code == 3

    @pytest.mark.parametrize(
        "eta",
        [at(14, 0, 1), at(14, 30), at(14, 59, 59)],
        ids=["one-second-after", "half-past", "one-second-before"],
    )
    def test_anywhere_within_an_hour_uses_the_hour_ending_after_it(self, eta: datetime) -> None:
        assert select_weather(series(), eta).snow_in_hr == 3.0

    def test_wind_is_interpolated_between_the_surrounding_hours(self) -> None:
        sample = select_weather(series(), at(14, 20))

        assert sample.wind_mph == pytest.approx(30.0 + 10.0 / 3)
        assert sample.gust_mph == pytest.approx(35.0 + 10.0 / 3)

    def test_wind_at_half_past_is_the_midpoint(self) -> None:
        assert select_weather(series(), at(14, 30)).wind_mph == pytest.approx(35.0)

    def test_first_and_last_entries_are_selectable(self) -> None:
        first = select_weather(series(), at(12))
        last = select_weather(series(), at(17))

        assert (first.wind_mph, first.snow_in_hr) == (10.0, 0.0)
        assert (last.wind_mph, last.snow_in_hr) == (60.0, 5.0)

    def test_eta_in_another_timezone_selects_the_same_instant(self) -> None:
        eta = at(14, 20).astimezone(timezone(timedelta(hours=-6)))

        assert select_weather(series(), eta) == select_weather(series(), at(14, 20))


class TestOutsideTheSeries:
    def test_eta_after_the_last_entry_is_unknown(self) -> None:
        assert select_weather(series(), at(17, 20)) == WeatherSample()

    def test_eta_a_day_later_is_unknown(self) -> None:
        assert select_weather(series(), at(14) + timedelta(days=1)) == WeatherSample()

    def test_eta_before_the_first_entry_is_unknown(self) -> None:
        assert select_weather(series(), at(11)) == WeatherSample()

    def test_precipitation_just_before_the_start_uses_the_first_entry(self) -> None:
        sample = select_weather(series(), at(11, 30))

        assert sample.wind_mph is None
        assert sample.snow_in_hr == 0.0

    def test_wind_needs_both_surrounding_hours(self) -> None:
        sample = select_weather(series(), at(17, 30))

        assert sample.wind_mph is None


class TestMissingValues:
    NULL_AT_15 = (10.0, 20.0, 30.0, None, 50.0, 60.0)

    def test_wind_is_unknown_when_a_surrounding_hour_is_missing(self) -> None:
        sample = select_weather(series(wind_mph=self.NULL_AT_15), at(14, 20))

        assert sample.wind_mph is None
        assert sample.gust_mph is not None

    def test_wind_on_the_hour_only_needs_that_hour(self) -> None:
        sample = select_weather(series(wind_mph=self.NULL_AT_15), at(14))

        assert sample.wind_mph == 30.0

    def test_missing_wind_on_the_hour_is_unknown(self) -> None:
        assert select_weather(series(wind_mph=self.NULL_AT_15), at(15)).wind_mph is None

    def test_missing_rain_makes_the_rain_rate_unknown_not_zero(self) -> None:
        sample = select_weather(series(rain_in=(0.0, 0.1, 0.2, None, 0.4, 0.5)), at(14, 20))

        assert sample.rain_in_hr is None

    def test_missing_showers_make_the_rain_rate_unknown_not_rain_only(self) -> None:
        sample = select_weather(series(showers_in=(0.0, 0.0, 0.0, None, 0.0, 0.0)), at(14, 20))

        assert sample.rain_in_hr is None

    def test_missing_snowfall_is_unknown(self) -> None:
        sample = select_weather(series(snowfall_in=(0.0, 0.0, 0.0, None, 0.0, 0.0)), at(14, 20))

        assert sample.snow_in_hr is None
        assert sample.rain_in_hr is not None

    def test_missing_weather_code_is_unknown(self) -> None:
        sample = select_weather(series(weather_code=(0, 0, 0, None, 0, 0)), at(14, 20))

        assert sample.weather_code is None


class TestRainRate:
    def test_rain_rate_is_rain_plus_showers(self) -> None:
        sample = select_weather(series(), at(13))

        assert sample.rain_in_hr == pytest.approx(0.11)

    def test_float_noise_does_not_push_the_sum_below_a_band_edge(self) -> None:
        noisy = series(rain_in=(0.01,) * HOURS, showers_in=(0.09,) * HOURS)

        sample = select_weather(noisy, at(13))

        assert 0.01 + 0.09 < 0.1  # the raw float sum would read as LOW
        assert sample.rain_in_hr == 0.1
        assert classify_rain(sample.rain_in_hr) is RiskLevel.MODERATE


@given(
    minutes=st.integers(min_value=0, max_value=5 * 60),
    wind=st.lists(st.floats(min_value=0, max_value=100), min_size=HOURS, max_size=HOURS),
)
def test_interpolated_wind_stays_between_the_surrounding_hours(
    minutes: int, wind: list[float]
) -> None:
    eta = START + timedelta(minutes=minutes)
    floor_index, remainder = divmod(minutes, 60)
    expected_range = [wind[floor_index]] + ([wind[floor_index + 1]] if remainder else [])

    result = select_weather(series(wind_mph=tuple(wind)), eta).wind_mph

    assert result is not None
    assert min(expected_range) - 1e-9 <= result <= max(expected_range) + 1e-9


@given(minutes=st.integers(min_value=0, max_value=5 * 60))
def test_precipitation_is_always_the_value_at_the_next_hour_mark(minutes: int) -> None:
    eta = START + timedelta(minutes=minutes)
    ceil_index = -(-minutes // 60)  # ceiling division

    result = select_weather(series(), eta)

    assert result.snow_in_hr == float(ceil_index)
