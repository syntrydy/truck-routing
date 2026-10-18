"""The brief's rules as plain cases, to read beside the brief.

Each section is one rule of the brief, in its order, and each line is one case: the reading,
the load where it matters, and the level a truck is told. Nothing here is clever on purpose.
If you read the brief differently from a line, that line is the place to say so; the thinking
behind the edges is in docs/adr/0002-risk-boundaries.md, and SPEC section 4.5 has the table.

The detailed, property and boundary tests of the same code are in ``test_risk.py`` and
``test_assess.py``; this file is the short version that can be checked by eye.
"""

import pytest

from planner.domain.models import RiskLevel, RouteScore, WeatherSample
from planner.domain.ranking import ScoredRoute, rank_routes
from planner.domain.risk import WindBasis, assess

LOW = RiskLevel.LOW
MODERATE = RiskLevel.MODERATE
HIGH = RiskLevel.HIGH
SEVERE = RiskLevel.SEVERE
NO_TRAVEL = RiskLevel.NO_TRAVEL
UNKNOWN = RiskLevel.UNKNOWN

EMPTY_TRUCK_LB = 0
LIGHT_LB = 20_000


def reading(
    wind_mph: float = 0.0,
    rain_in_hr: float = 0.0,
    snow_in_hr: float = 0.0,
    gust_mph: float | None = None,
) -> WeatherSample:
    """A complete reading, calm in whatever is not given."""
    return WeatherSample(
        wind_mph=wind_mph, gust_mph=gust_mph, rain_in_hr=rain_in_hr, snow_in_hr=snow_in_hr
    )


def level(sample: WeatherSample, load_lb: float = LIGHT_LB) -> RiskLevel:
    return assess(sample, load_lb).level


class TestWind:
    """Wind (mph): below 25 Low, 25 up to 35 Moderate, 35 up to 45 High, 45 up to 55 Severe,
    55 and over No Travel. A band includes its lower edge, so exactly 25 mph is Moderate."""

    @pytest.mark.parametrize(
        ("wind_mph", "expected"),
        [
            (0, LOW),
            (24.99, LOW),
            (25, MODERATE),
            (34.99, MODERATE),
            (35, HIGH),
            (44.99, HIGH),
            (45, SEVERE),
            (54.99, SEVERE),
            (55, NO_TRAVEL),
            (80, NO_TRAVEL),
        ],
    )
    def test_wind_of(self, wind_mph: float, expected: RiskLevel) -> None:
        assert level(reading(wind_mph=wind_mph), EMPTY_TRUCK_LB) is expected

    def test_a_gust_does_not_count_unless_the_wind_basis_says_so(self) -> None:
        sample = reading(wind_mph=20, gust_mph=50)

        assert assess(sample, LIGHT_LB).level is LOW
        assert assess(sample, LIGHT_LB, WindBasis.GUST).level is SEVERE


class TestRain:
    """Rain (inches per hour): below 0.10 Low, 0.10 up to 0.25 Moderate, 0.25 up to 0.50 High,
    0.50 up to and including 1.00 Severe, above 1.00 No Travel."""

    @pytest.mark.parametrize(
        ("rain_in_hr", "expected"),
        [
            (0, LOW),
            (0.09, LOW),
            (0.10, MODERATE),
            (0.24, MODERATE),
            (0.25, HIGH),
            (0.49, HIGH),
            (0.50, SEVERE),
            (1.00, SEVERE),
            (1.01, NO_TRAVEL),
        ],
    )
    def test_rain_of(self, rain_in_hr: float, expected: RiskLevel) -> None:
        assert level(reading(wind_mph=0, rain_in_hr=rain_in_hr)) is expected


class TestSnow:
    """Snow (inches per hour): below 0.5 Low, 0.5 up to 1.0 Moderate, 1.0 up to 2.0 High,
    2.0 up to and including 3.0 Severe, above 3.0 No Travel."""

    @pytest.mark.parametrize(
        ("snow_in_hr", "expected"),
        [
            (0, LOW),
            (0.4, LOW),
            (0.5, MODERATE),
            (0.9, MODERATE),
            (1.0, HIGH),
            (1.9, HIGH),
            (2.0, SEVERE),
            (3.0, SEVERE),
            (3.1, NO_TRAVEL),
        ],
    )
    def test_snow_of(self, snow_in_hr: float, expected: RiskLevel) -> None:
        assert level(reading(wind_mph=0, snow_in_hr=snow_in_hr)) is expected


class TestLoadRules:
    """A heavy truck is hurt more by wind, in three rules:
    wind of 55 or more is No Travel whatever the load;
    wind from 45 up to 55 with a load over 30,000 lb is No Travel;
    wind from 35 up to 45 with a load over 40,000 lb is Severe.
    "Over" is strict: exactly 30,000 lb, or exactly 40,000 lb, is not over."""

    @pytest.mark.parametrize(
        ("wind_mph", "load_lb", "expected"),
        [
            # 55 mph and more: No Travel for any load, even an empty truck.
            (55, 0, NO_TRAVEL),
            (55, 80_000, NO_TRAVEL),
            # 45 up to 55 mph: Severe, but No Travel above 30,000 lb.
            (47, 30_000, SEVERE),
            (47, 30_001, NO_TRAVEL),
            (45, 30_001, NO_TRAVEL),
            (54.99, 30_001, NO_TRAVEL),
            (45, 30_000, SEVERE),
            (45, 0, SEVERE),
            # 35 up to 45 mph: High, but Severe above 40,000 lb.
            (40, 40_000, HIGH),
            (40, 40_001, SEVERE),
            (35, 40_001, SEVERE),
            (44.99, 40_001, SEVERE),
            (35, 40_000, HIGH),
            # Below 35 mph the load changes nothing.
            (34.99, 80_000, MODERATE),
            (24.99, 80_000, LOW),
        ],
    )
    def test_wind_with_a_load(self, wind_mph: float, load_lb: float, expected: RiskLevel) -> None:
        assert level(reading(wind_mph=wind_mph), load_lb) is expected

    def test_the_load_rules_name_themselves_in_the_reason_a_driver_reads(self) -> None:
        reasons = assess(reading(wind_mph=47), 42_000).reasons

        assert reasons == ("Wind 47 mph → Severe", "Wind 47 mph with 42,000 lb load → No Travel")

    def test_a_negative_load_is_refused(self) -> None:
        with pytest.raises(ValueError, match="load"):
            assess(reading(wind_mph=10), -1)


class TestAPlaceTakesItsWorstFactor:
    """Wind, rain and snow are judged one by one; the place is as bad as its worst."""

    @pytest.mark.parametrize(
        ("sample", "expected"),
        [
            (reading(wind_mph=30, rain_in_hr=0.3), HIGH),  # Moderate wind, High rain
            (reading(wind_mph=50, rain_in_hr=0.0, snow_in_hr=0.6), SEVERE),
            (reading(wind_mph=10, rain_in_hr=0.6, snow_in_hr=3.5), NO_TRAVEL),
            (reading(wind_mph=10, rain_in_hr=0.05, snow_in_hr=0.1), LOW),
        ],
    )
    def test_the_worst_of_wind_rain_and_snow(
        self, sample: WeatherSample, expected: RiskLevel
    ) -> None:
        assert level(sample) is expected


class TestMissingWeatherNeverReadsAsSafe:
    """If a reading is missing the place is Unknown, not Low. Known danger is never hidden by
    a missing reading: a known Severe or worse stays."""

    @pytest.mark.parametrize(
        ("sample", "expected"),
        [
            (WeatherSample(wind_mph=None, rain_in_hr=0, snow_in_hr=0), UNKNOWN),
            (WeatherSample(wind_mph=10, rain_in_hr=None, snow_in_hr=0), UNKNOWN),
            (
                WeatherSample(wind_mph=None, rain_in_hr=0.3, snow_in_hr=0),
                UNKNOWN,
            ),  # only High known
            (WeatherSample(wind_mph=None, rain_in_hr=0.6, snow_in_hr=0), SEVERE),  # Severe stays
            (WeatherSample(wind_mph=None, rain_in_hr=2.0, snow_in_hr=0), NO_TRAVEL),
            (WeatherSample(), UNKNOWN),
        ],
    )
    def test_with_a_gap(self, sample: WeatherSample, expected: RiskLevel) -> None:
        assert level(sample) is expected


def route(  # noqa: PLR0913 - keyword-only test builder with defaults
    route_id: str,
    *,
    no_travel: float = 0.0,
    severe: float = 0.0,
    high: float = 0.0,
    avg_risk: float = 1.0,
    hours: float = 10.0,
) -> ScoredRoute:
    miles = {
        LOW: 0.0,
        MODERATE: 0.0,
        HIGH: high,
        SEVERE: severe,
        NO_TRAVEL: no_travel,
    }
    return ScoredRoute(
        route_id,
        RouteScore(
            distance_mi=500.0,
            duration_s=hours * 3_600,
            miles_by_level=miles,
            avg_risk=avg_risk,
        ),
    )


class TestRankingTheRoutes:
    """Routes are ranked on, in this order: miles of No Travel, miles of Severe, miles of High,
    average risk, then travel time. A later criterion only matters when every earlier one is a
    tie, and the recommendation is the first route. (The brief lists Severe first; No Travel is
    placed ahead of it so that a route with No Travel miles never beats one with only Severe.)"""

    def winner(self, *routes: ScoredRoute) -> str | None:
        return rank_routes(routes).recommended_route_id

    def test_fewer_no_travel_miles_win_whatever_else_is_worse(self) -> None:
        clean = route("clean", no_travel=0, severe=90, high=90, avg_risk=3.9, hours=20)
        quick = route("quick", no_travel=5, severe=0, high=0, avg_risk=0.1, hours=5)

        assert self.winner(quick, clean) == "clean"

    def test_then_fewer_severe_miles(self) -> None:
        assert self.winner(route("b", severe=8), route("a", severe=2.5, avg_risk=3.9)) == "a"

    def test_then_fewer_high_miles(self) -> None:
        assert self.winner(route("b", high=8), route("a", high=2.5, avg_risk=3.9)) == "a"

    def test_then_lower_average_risk(self) -> None:
        assert self.winner(route("b", avg_risk=1.5), route("a", avg_risk=0.5, hours=30)) == "a"

    def test_then_the_faster_route(self) -> None:
        assert self.winner(route("b", hours=12), route("a", hours=9)) == "a"

    def test_when_every_route_has_no_travel_miles_none_is_recommended(self) -> None:
        assert self.winner(route("a", no_travel=3), route("b", no_travel=9)) is None
