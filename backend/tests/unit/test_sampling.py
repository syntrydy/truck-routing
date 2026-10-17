import math
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from planner.domain.geometry import EARTH_RADIUS_M, METERS_PER_MILE, haversine_m
from planner.domain.models import LatLon
from planner.domain.sampling import (
    sample_checkpoints,
    stretch_lengths_mi,
    truck_durations_s,
)

DEPARTURE = datetime(2026, 1, 15, 8, 0, tzinfo=UTC)
DEGREES_PER_MILE = METERS_PER_MILE / (EARTH_RADIUS_M * math.pi / 180)
SECONDS_PER_HOUR = 3_600


def on_equator(*miles: float) -> list[LatLon]:
    """Points on the equator at the given cumulative mileposts (exact haversine miles)."""
    return [LatLon(0.0, mile * DEGREES_PER_MILE) for mile in miles]


def steady(points: list[LatLon], mph: float) -> list[float]:
    """Per-segment durations for constant driving at ``mph``."""
    return [
        haversine_m(a, b) / METERS_PER_MILE / mph * SECONDS_PER_HOUR
        for a, b in zip(points, points[1:], strict=False)
    ]


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


class TestSampleCheckpoints:
    def test_trip_shorter_than_the_interval_has_two_checkpoints(self) -> None:
        points = on_equator(0, 8)

        checkpoints = sample_checkpoints(points, steady(points, 50), DEPARTURE, 25)

        assert [c.distance_mi for c in checkpoints] == pytest.approx([0, 8])

    def test_destination_is_always_the_last_checkpoint(self) -> None:
        points = on_equator(0, 60)

        checkpoints = sample_checkpoints(points, steady(points, 50), DEPARTURE, 25)

        assert checkpoints[-1].location == points[-1]
        assert checkpoints[-1].distance_mi == pytest.approx(60)

    def test_positions_are_every_interval_then_the_destination(self) -> None:
        points = on_equator(0, 60)

        checkpoints = sample_checkpoints(points, steady(points, 50), DEPARTURE, 25)

        assert [c.distance_mi for c in checkpoints] == pytest.approx([0, 25, 50, 60])
        assert [c.index for c in checkpoints] == [0, 1, 2, 3]

    def test_trip_that_is_an_exact_multiple_has_no_duplicate_destination(self) -> None:
        points = on_equator(0, 100)

        checkpoints = sample_checkpoints(points, steady(points, 50), DEPARTURE, 25)

        assert [c.distance_mi for c in checkpoints] == pytest.approx([0, 25, 50, 75, 100])

    def test_sample_a_sliver_before_the_destination_is_dropped(self) -> None:
        points = on_equator(0, 50.0001)  # 0.16 m past the 50-mile mark

        checkpoints = sample_checkpoints(points, steady(points, 50), DEPARTURE, 25)

        assert [round(c.distance_mi, 3) for c in checkpoints] == [0, 25, 50.0]
        assert checkpoints[-1].distance_mi == pytest.approx(50.0001)

    @pytest.mark.parametrize(("interval", "expected_count"), [(10, 11), (25, 5), (50, 3)])
    def test_checkpoint_count_for_a_100_mile_trip(self, interval: int, expected_count: int) -> None:
        points = on_equator(0, 100)

        checkpoints = sample_checkpoints(points, steady(points, 50), DEPARTURE, interval)

        assert len(checkpoints) == expected_count

    def test_first_checkpoint_is_the_origin_at_departure_time(self) -> None:
        points = on_equator(0, 40)

        first = sample_checkpoints(points, steady(points, 50), DEPARTURE, 25)[0]

        assert first.location == points[0]
        assert first.distance_mi == 0.0
        assert first.eta == DEPARTURE

    def test_eta_follows_constant_speed(self) -> None:
        points = on_equator(0, 100)

        checkpoints = sample_checkpoints(points, steady(points, 50), DEPARTURE, 25)

        offsets = [(c.eta - DEPARTURE).total_seconds() / 60 for c in checkpoints]
        assert offsets == pytest.approx([0, 30, 60, 90, 120])

    def test_eta_interpolates_across_segments_of_different_speed(self) -> None:
        points = on_equator(0, 10, 20)
        durations = [600.0, 1800.0]  # 60 mph then 20 mph

        checkpoints = sample_checkpoints(points, durations, DEPARTURE, 15)

        assert [c.distance_mi for c in checkpoints] == pytest.approx([0, 15, 20])
        assert (checkpoints[1].eta - DEPARTURE).total_seconds() == pytest.approx(600 + 900)
        assert (checkpoints[2].eta - DEPARTURE).total_seconds() == pytest.approx(2400)

    def test_location_is_interpolated_on_the_geometry(self) -> None:
        points = on_equator(0, 10, 50)

        checkpoints = sample_checkpoints(points, steady(points, 50), DEPARTURE, 25)

        assert checkpoints[1].location.lat == pytest.approx(0.0, abs=1e-9)
        assert checkpoints[1].location.lon == pytest.approx(25 * DEGREES_PER_MILE)

    def test_etas_are_strictly_increasing(self) -> None:
        points = on_equator(0, 3, 80, 81, 130)

        checkpoints = sample_checkpoints(points, steady(points, 55), DEPARTURE, 10)

        etas = [c.eta for c in checkpoints]
        assert all(a < b for a, b in zip(etas, etas[1:], strict=False))

    def test_duplicate_points_in_the_geometry_are_tolerated(self) -> None:
        points = [*on_equator(0, 10), LatLon(0.0, 10 * DEGREES_PER_MILE), *on_equator(30)]
        durations = [*steady(points, 50)]

        checkpoints = sample_checkpoints(points, durations, DEPARTURE, 25)

        assert [c.distance_mi for c in checkpoints] == pytest.approx([0, 25, 30])

    def test_etas_are_in_the_departure_timezone(self) -> None:
        points = on_equator(0, 40)

        checkpoints = sample_checkpoints(points, steady(points, 50), DEPARTURE, 25)

        assert all(c.eta.tzinfo is UTC for c in checkpoints)

    @pytest.mark.parametrize("interval", [0, -10])
    def test_rejects_non_positive_interval(self, interval: float) -> None:
        points = on_equator(0, 10)

        with pytest.raises(ValueError, match="interval"):
            sample_checkpoints(points, steady(points, 50), DEPARTURE, interval)

    def test_rejects_a_route_with_no_length(self) -> None:
        points = [LatLon(1.0, 1.0), LatLon(1.0, 1.0)]

        with pytest.raises(ValueError, match="no length"):
            sample_checkpoints(points, [10.0], DEPARTURE, 25)

    def test_rejects_mismatched_durations(self) -> None:
        with pytest.raises(ValueError, match="one duration per segment"):
            sample_checkpoints(on_equator(0, 5, 10), [60.0], DEPARTURE, 25)

    @given(
        total_mi=st.floats(min_value=1, max_value=600),
        interval=st.sampled_from([10, 25, 50]),
        mph=st.floats(min_value=20, max_value=65),
    )
    def test_invariants_hold_for_any_trip(self, total_mi: float, interval: int, mph: float) -> None:
        points = on_equator(0, total_mi / 3, total_mi)
        durations = steady(points, mph)

        checkpoints = sample_checkpoints(points, durations, DEPARTURE, interval)
        lengths = stretch_lengths_mi(checkpoints)

        assert checkpoints[0].distance_mi == 0.0
        assert checkpoints[-1].distance_mi == pytest.approx(total_mi)
        assert checkpoints[-1].location == points[-1]
        assert len(checkpoints) >= 2
        distances = [c.distance_mi for c in checkpoints]
        etas = [c.eta for c in checkpoints]
        assert all(a < b for a, b in zip(distances, distances[1:], strict=False))
        assert all(a < b for a, b in zip(etas, etas[1:], strict=False))
        assert all(0 < length <= interval + 1e-6 for length in lengths)
        assert sum(lengths) == pytest.approx(total_mi)
        assert checkpoints[-1].eta - DEPARTURE == pytest.approx(
            timedelta(seconds=sum(durations)), abs=timedelta(milliseconds=1)
        )


class TestStretchLengths:
    def test_each_stretch_runs_to_the_next_checkpoint(self) -> None:
        points = on_equator(0, 60)
        checkpoints = sample_checkpoints(points, steady(points, 50), DEPARTURE, 25)

        assert stretch_lengths_mi(checkpoints) == pytest.approx([25, 25, 10])

    def test_last_stretch_is_shorter_than_the_interval(self) -> None:
        points = on_equator(0, 60)
        checkpoints = sample_checkpoints(points, steady(points, 50), DEPARTURE, 25)

        assert stretch_lengths_mi(checkpoints)[-1] < 25

    def test_short_trip_is_a_single_stretch(self) -> None:
        points = on_equator(0, 8)
        checkpoints = sample_checkpoints(points, steady(points, 50), DEPARTURE, 25)

        assert stretch_lengths_mi(checkpoints) == pytest.approx([8])

    def test_no_checkpoints_means_no_stretches(self) -> None:
        assert stretch_lengths_mi([]) == []
