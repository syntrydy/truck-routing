import json
import logging
import sys

import pytest

from planner.infra.jsonlog import (
    JsonFormatter,
    RequestIdFilter,
    request_id_var,
    truncate_coordinates,
)


def record(message: str = "hello", *args: object, **extra: object) -> logging.LogRecord:
    made = logging.LogRecord("planner.test", logging.INFO, __file__, 1, message, args or None, None)
    for key, value in extra.items():
        setattr(made, key, value)
    return made


def line(made: logging.LogRecord) -> dict[str, object]:
    RequestIdFilter().filter(made)
    return json.loads(JsonFormatter().format(made))  # type: ignore[no-any-return]


class TestTruncateCoordinates:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("41.8781,-87.6298", "41.87,-87.62"),
            ("lat=41.8781&lon=-87.6298", "lat=41.87&lon=-87.62"),
            ("-104.99031 and 39.7392", "-104.99 and 39.73"),
            (
                "route/v1/driving/-87.6298,41.8781;-104.9903,39.7392",
                "route/v1/driving/-87.62,41.87;-104.99,39.73",
            ),
            ("41.87 stays", "41.87 stays"),
            ("41.8 stays", "41.8 stays"),
            ("no numbers", "no numbers"),
        ],
    )
    def test_long_decimals_are_cut_not_rounded(self, text: str, expected: str) -> None:
        assert truncate_coordinates(text) == expected

    @pytest.mark.parametrize(
        "text", ["10.100.200.5", "from 203.0.113.9", "version 3.12.1", "1234.5678"]
    )
    def test_other_dotted_numbers_are_left_alone(self, text: str) -> None:
        assert truncate_coordinates(text) == text


class TestJsonFormatter:
    def test_a_record_is_one_json_line_with_the_usual_fields(self) -> None:
        output = JsonFormatter().format(record("hi %s", "there"))

        assert "\n" not in output
        body = json.loads(output)
        assert body["message"] == "hi there"
        assert (body["level"], body["logger"]) == ("INFO", "planner.test")
        assert body["time"].endswith("+00:00")

    def test_the_request_id_is_stamped_by_the_filter(self) -> None:
        token = request_id_var.set("abc123")
        try:
            assert line(record())["request_id"] == "abc123"
        finally:
            request_id_var.reset(token)

    def test_without_a_request_the_id_is_empty(self) -> None:
        assert line(record())["request_id"] == ""

    def test_extra_fields_are_top_level_and_keep_their_structure(self) -> None:
        body = line(record(plan={"duration_ms": 12, "upstream": {"osrm": {"calls": 1}}}))

        assert body["plan"] == {"duration_ms": 12, "upstream": {"osrm": {"calls": 1}}}

    def test_coordinates_are_cut_in_the_message_and_in_extra_strings(self) -> None:
        body = line(record("failed at 41.8781,-87.6298", where=["39.7392,-104.9903"]))

        assert body["message"] == "failed at 41.87,-87.62"
        assert body["where"] == ["39.73,-104.99"]

    def test_numbers_are_not_touched(self) -> None:
        assert line(record(ratio=0.12345))["ratio"] == 0.12345

    def test_an_exception_is_included_with_its_coordinates_cut(self) -> None:
        try:
            msg = "bad point 41.8781,-87.6298"
            raise ValueError(msg)  # noqa: TRY301
        except ValueError:
            made = record()
            made.exc_info = sys.exc_info()

        exception = str(line(made)["exception"])

        assert "ValueError: bad point 41.87,-87.62" in exception

    def test_values_json_cannot_hold_are_written_as_text(self) -> None:
        assert line(record(thing=object()))["thing"].startswith("<object")  # type: ignore[attr-defined]
