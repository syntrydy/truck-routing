"""Structured JSON logs (SPEC sections 8 and 9).

One JSON object per line on stdout. Every record carries the ``request_id`` of the request
being served, and no coordinate leaves this module with more than two decimals.
"""

import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# The ID of the request being served; set by the request-ID middleware, empty outside one.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")

COORDINATE_DECIMALS = 2  # about 1 km: enough to debug a region, too coarse to follow a truck
# A decimal number with a short integer part and more than two decimals, such as a latitude.
# It is not part of a longer dotted number (an IP address or a version).
_LONG_DECIMAL = re.compile(rf"(?<![\w.])(-?\d{{1,3}}\.\d{{{COORDINATE_DECIMALS}}})\d+(?!\d|\.\d)")
_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
    "request_id",
}


def truncate_coordinates(text: str) -> str:
    """``text`` with every long decimal number cut (not rounded) to two decimals."""
    return _LONG_DECIMAL.sub(r"\1", text)


def _clean(value: Any) -> Any:  # noqa: ANN401 - any JSON value
    """``value`` with the coordinates in its strings truncated."""
    if isinstance(value, str):
        return truncate_coordinates(value)
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(item) for item in value]
    return value


class RequestIdFilter(logging.Filter):
    """Stamps each record with the ID of the request being served."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """Formats a record as one line of JSON, with its ``extra`` fields at the top level."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", ""),
        }
        payload.update(
            {key: value for key, value in record.__dict__.items() if key not in _RESERVED}
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(_clean(payload), default=str, separators=(",", ":"))
