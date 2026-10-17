from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from rest_framework.exceptions import ValidationError

from planner.api.errors import first_validation_error
from planner.api.serializers import OffsetDateTimeField, parse_plan_request
from planner.domain.models import LatLon
from planner.services.models import PlanRequest

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
DEPARTURE = "2026-10-18T06:00:00-05:00"


def body(**changes: Any) -> dict[str, Any]:
    """A valid request body with some fields replaced (a ``...`` value removes the field)."""
    values: dict[str, Any] = {
        "origin": {"lat": 41.8781, "lon": -87.6298, "label": "Chicago, IL"},
        "destination": {"lat": 39.7392, "lon": -104.9903, "label": "Denver, CO"},
        "departure_at": DEPARTURE,
        "load_lb": 42_000,
        "interval_mi": 25,
    }
    for key, value in changes.items():
        if value is ...:
            del values[key]
        else:
            values[key] = value
    return values


def point(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {"lat": 41.8781, "lon": -87.6298, "label": "Chicago, IL"}
    for key, value in changes.items():
        if value is ...:
            del values[key]
        else:
            values[key] = value
    return values


def rejection(data: Any, now: datetime = NOW) -> tuple[str | None, str]:  # noqa: ANN401
    with pytest.raises(ValidationError) as raised:
        parse_plan_request(data, now)
    return first_validation_error(raised.value.detail)


class TestAValidRequest:
    def test_it_becomes_a_plan_request(self) -> None:
        request = parse_plan_request(body(), NOW)

        assert request == PlanRequest(
            origin=LatLon(41.8781, -87.6298),
            destination=LatLon(39.7392, -104.9903),
            departure=datetime.fromisoformat(DEPARTURE),
            load_lb=42_000,
            interval_mi=25,
        )

    def test_labels_are_optional(self) -> None:
        data = body(origin=point(label=...), destination=point(label=...))

        assert parse_plan_request(data, NOW).load_lb == 42_000

    def test_a_blank_label_is_allowed(self) -> None:
        assert parse_plan_request(body(origin=point(label="")), NOW)

    def test_integers_are_accepted_for_coordinates(self) -> None:
        data = body(origin=point(lat=41, lon=-87), destination=point(lat=39, lon=-104))

        request = parse_plan_request(data, NOW)

        assert (request.origin.lat, request.origin.lon) == (41.0, -87.0)

    def test_the_departure_keeps_its_offset(self) -> None:
        request = parse_plan_request(body(), NOW)

        assert request.departure.utcoffset() == timedelta(hours=-5)


class TestCoordinates:
    @pytest.mark.parametrize("side", ["origin", "destination"])
    @pytest.mark.parametrize(
        ("field", "value"),
        [("lat", 90), ("lat", -90), ("lon", 180), ("lon", -180), ("lat", 0), ("lon", 0)],
    )
    def test_the_edges_of_the_ranges_are_valid(self, side: str, field: str, value: float) -> None:
        assert parse_plan_request(body(**{side: point(**{field: value})}), NOW)

    @pytest.mark.parametrize("side", ["origin", "destination"])
    @pytest.mark.parametrize(
        ("field", "value"),
        [("lat", 90.0001), ("lat", -90.0001), ("lon", 180.0001), ("lon", -180.0001), ("lat", 1e9)],
    )
    def test_just_beyond_the_ranges_is_refused(self, side: str, field: str, value: float) -> None:
        found = rejection(body(**{side: point(**{field: value})}))

        assert found[0] == f"{side}.{field}"
        assert "Ensure this value is" in found[1]

    @pytest.mark.parametrize("value", ["41.8", True, False, None, [], {}, "north"])
    def test_a_coordinate_must_be_a_json_number(self, value: Any) -> None:
        field, _ = rejection(body(origin=point(lat=value)))

        assert field == "origin.lat"

    @pytest.mark.parametrize("field", ["lat", "lon"])
    def test_a_missing_coordinate_is_refused(self, field: str) -> None:
        found = rejection(body(destination=point(**{field: ...})))

        assert found == (f"destination.{field}", "This field is required.")

    @pytest.mark.parametrize("value", [None, [], "Denver", 5])
    def test_a_point_must_be_an_object(self, value: Any) -> None:
        field, _ = rejection(body(origin=value))

        assert field == "origin"

    def test_a_missing_point_is_refused(self) -> None:
        assert rejection(body(destination=...)) == ("destination", "This field is required.")


class TestLabels:
    def test_200_characters_are_allowed(self) -> None:
        assert parse_plan_request(body(origin=point(label="x" * 200)), NOW)

    def test_201_characters_are_refused(self) -> None:
        found = rejection(body(origin=point(label="x" * 201)))

        assert found[0] == "origin.label"
        assert "no more than 200" in found[1]

    def test_the_destination_label_is_checked_too(self) -> None:
        assert rejection(body(destination=point(label="x" * 201)))[0] == "destination.label"

    def test_unicode_labels_are_fine(self) -> None:
        assert parse_plan_request(body(origin=point(label="São Paulo, 東京 ✓")), NOW)

    @pytest.mark.parametrize("value", [None, 5, [], {}])
    def test_a_label_must_be_text(self, value: Any) -> None:
        assert rejection(body(origin=point(label=value)))[0] == "origin.label"


class TestDeparture:
    def test_it_must_state_a_utc_offset(self) -> None:
        found = rejection(body(departure_at="2026-10-18T06:00:00"))

        assert found[0] == "departure_at"
        assert "UTC offset" in found[1]

    @pytest.mark.parametrize(
        "value",
        ["2026-10-18", "tomorrow", "", "2026-13-40T00:00:00Z", 1_792_000_000, None, True, []],
    )
    def test_it_must_be_an_iso_date_and_time(self, value: Any) -> None:
        assert rejection(body(departure_at=value))[0] == "departure_at"

    @pytest.mark.parametrize(
        "value", ["2026-10-18T06:00:00Z", "2026-10-18T06:00:00+00:00", "2026-10-18T06:00:00+05:30"]
    )
    def test_z_and_numeric_offsets_are_accepted(self, value: str) -> None:
        assert parse_plan_request(body(departure_at=value), NOW).departure.utcoffset() is not None

    def test_it_is_required(self) -> None:
        assert rejection(body(departure_at=...)) == ("departure_at", "This field is required.")

    def test_exactly_seven_days_ahead_is_allowed(self) -> None:
        later = NOW + timedelta(days=7)

        assert parse_plan_request(body(departure_at=later.isoformat()), NOW).departure == later

    def test_one_second_beyond_seven_days_is_refused(self) -> None:
        later = NOW + timedelta(days=7, seconds=1)

        found = rejection(body(departure_at=later.isoformat()))

        assert found == ("departure_at", "The departure time must be within the next 7 days.")

    def test_the_week_is_counted_from_now_whatever_the_offset(self) -> None:
        later = (NOW + timedelta(days=7)).astimezone(timezone(timedelta(hours=14)))

        assert parse_plan_request(body(departure_at=later.isoformat()), NOW)

    def test_a_future_time_is_kept_as_it_is(self) -> None:
        later = NOW + timedelta(hours=3, microseconds=123)

        assert parse_plan_request(body(departure_at=later.isoformat()), NOW).departure == later

    def test_just_in_the_past_is_moved_to_now(self) -> None:
        recent = NOW - timedelta(minutes=1)

        assert parse_plan_request(body(departure_at=recent.isoformat()), NOW).departure == NOW

    def test_exactly_fifteen_minutes_ago_is_allowed_and_moved_to_now(self) -> None:
        edge = NOW - timedelta(minutes=15)

        assert parse_plan_request(body(departure_at=edge.isoformat()), NOW).departure == NOW

    def test_just_over_fifteen_minutes_ago_is_refused(self) -> None:
        past = NOW - timedelta(minutes=15, seconds=1)

        found = rejection(body(departure_at=past.isoformat()))

        assert found == ("departure_at", "The departure time is in the past.")

    def test_exactly_now_is_allowed(self) -> None:
        assert parse_plan_request(body(departure_at=NOW.isoformat()), NOW).departure == NOW

    def test_the_window_follows_the_clock_it_is_given(self) -> None:
        later_now = NOW + timedelta(days=30)

        assert rejection(body(), now=later_now)[0] == "departure_at"


class TestLoad:
    @pytest.mark.parametrize("value", [0, 1, 80_000, 200_000])
    def test_whole_numbers_from_0_to_200000_are_valid(self, value: int) -> None:
        assert parse_plan_request(body(load_lb=value), NOW).load_lb == value

    @pytest.mark.parametrize("value", [-1, 200_001, 10**9])
    def test_outside_the_range_is_refused(self, value: int) -> None:
        found = rejection(body(load_lb=value))

        assert found[0] == "load_lb"
        assert "Ensure this value is" in found[1]

    @pytest.mark.parametrize("value", [100.5, 100.0, "100", True, False, None, [], {}])
    def test_it_must_be_a_json_integer(self, value: Any) -> None:
        assert rejection(body(load_lb=value)) == ("load_lb", rejection(body(load_lb=value))[1])

    def test_a_float_gets_a_clear_message(self) -> None:
        assert rejection(body(load_lb=100.5)) == ("load_lb", "A whole number is required.")

    def test_it_is_required(self) -> None:
        assert rejection(body(load_lb=...)) == ("load_lb", "This field is required.")


class TestInterval:
    @pytest.mark.parametrize("value", [10, 25, 50])
    def test_the_three_intervals_are_valid(self, value: int) -> None:
        assert parse_plan_request(body(interval_mi=value), NOW).interval_mi == value

    @pytest.mark.parametrize("value", [0, 5, 9, 11, 24, 26, 30, 49, 51, 100, -25])
    def test_anything_else_is_refused(self, value: int) -> None:
        assert rejection(body(interval_mi=value)) == ("interval_mi", "Must be one of 10, 25, 50.")

    @pytest.mark.parametrize("value", ["25", 25.0, 25.5, True, None, [], {}])
    def test_it_must_be_a_json_integer(self, value: Any) -> None:
        assert rejection(body(interval_mi=value))[0] == "interval_mi"

    def test_it_is_required(self) -> None:
        assert rejection(body(interval_mi=...)) == ("interval_mi", "This field is required.")


class TestUnknownFieldsAndShape:
    def test_an_unknown_top_level_field_is_refused(self) -> None:
        assert rejection({**body(), "load_kg": 100}) == ("load_kg", "Unknown field.")

    def test_an_unknown_field_in_a_point_is_refused(self) -> None:
        found = rejection(body(origin=point(altitude=12)))

        assert found == ("origin.altitude", "Unknown field.")

    @pytest.mark.parametrize("data", [[], "text", 5, None, [body()]])
    def test_the_body_must_be_an_object(self, data: Any) -> None:
        field, message = rejection(data)

        assert field is None
        assert message

    def test_an_empty_object_reports_the_first_missing_field(self) -> None:
        assert rejection({}) == ("origin", "This field is required.")

    def test_the_first_error_in_field_order_is_the_one_reported(self) -> None:
        found = rejection(body(load_lb=-1, interval_mi=5, origin=point(lat=500)))

        assert found[0] == "origin.lat"


def test_a_departure_is_written_back_as_iso_8601_with_its_offset() -> None:
    moment = datetime(2026, 10, 18, 6, 0, tzinfo=timezone(timedelta(hours=-5)))

    assert OffsetDateTimeField().to_representation(moment) == "2026-10-18T06:00:00-05:00"
