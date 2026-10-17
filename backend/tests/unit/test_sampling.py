import math

import pytest

from planner.domain.geometry import EARTH_RADIUS_M, METERS_PER_MILE
from planner.domain.models import LatLon
from planner.domain.sampling import truck_durations_s

DEGREES_PER_MILE = METERS_PER_MILE / (EARTH_RADIUS_M * math.pi / 180)
SECONDS_PER_HOUR = 3_600


def on_equator(*miles: float) -> list[LatLon]:
    """Points on the equator at the given cumulative mileposts (exact haversine miles)."""
    return [LatLon(0.0, mile * DEGREES_PER_MILE) for mile in miles]


class TestTruckDurations:
    def test_fast_segment_is_slowed_to_the_speed_cap(self) -> None:
        points = on_equator(0, 65)
        fast = [SECONDS_PER_HOUR / 2]  # 130 mph

        assert truck_durations_s(points, fast, 65.0) == pytest.approx([SECONDS_PER_HOUR])

    def test_slow_segment_is_untouched(self) -> None:
        points = on_equator(0, 30)
        slow = [SECONDS_PER_HOUR]  # 30 mph

        assert truck_durations_s(points, slow, 65.0) == [SECONDS_PER_HOUR]

    def test_each_segment_is_capped_on_its_own(self) -> None:
        points = on_equator(0, 65, 95)
        durations = [SECONDS_PER_HOUR / 2, SECONDS_PER_HOUR]

        result = truck_durations_s(points, durations, 65.0)

        assert result[0] == pytest.approx(SECONDS_PER_HOUR)
        assert result[1] == SECONDS_PER_HOUR

    def test_exactly_at_the_cap_is_unchanged(self) -> None:
        points = on_equator(0, 65)

        result = truck_durations_s(points, [SECONDS_PER_HOUR], 65.0)

        assert result == pytest.approx([SECONDS_PER_HOUR])

    def test_zero_length_segment_keeps_the_provider_time(self) -> None:
        points = [LatLon(0.0, 0.0), LatLon(0.0, 0.0)]

        assert truck_durations_s(points, [12.0], 65.0) == [12.0]

    @pytest.mark.parametrize("speed", [0.0, -5.0])
    def test_rejects_non_positive_speed(self, speed: float) -> None:
        with pytest.raises(ValueError, match="positive"):
            truck_durations_s(on_equator(0, 1), [60.0], speed)

    def test_rejects_wrong_number_of_durations(self) -> None:
        with pytest.raises(ValueError, match="one duration per segment"):
            truck_durations_s(on_equator(0, 1, 2), [60.0], 65.0)

    def test_rejects_surplus_durations(self) -> None:
        with pytest.raises(ValueError, match="one duration per segment"):
            truck_durations_s(on_equator(0, 1), [60.0, 60.0], 65.0)

    def test_rejects_negative_duration(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            truck_durations_s(on_equator(0, 1), [-1.0], 65.0)

    def test_rejects_a_single_point_route(self) -> None:
        with pytest.raises(ValueError, match="two points"):
            truck_durations_s(on_equator(0), [], 65.0)
