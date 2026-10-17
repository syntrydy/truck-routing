"""Shared by the endpoint tests: a valid request body and scripted providers behind the view."""

import json
from datetime import UTC, datetime
from typing import Any

from rest_framework.test import APIClient

from planner.domain.geometry import destination_point
from tests.services.stubs import START, route

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
ORIGIN = {"lat": START.lat, "lon": START.lon, "label": "Boulder, CO"}
DESTINATION = {
    "lat": destination_point(START, 90.0, 96_000).lat,
    "lon": destination_point(START, 90.0, 96_000).lon,
    "label": "East of Boulder",
}


def valid_body(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "origin": ORIGIN,
        "destination": DESTINATION,
        "departure_at": "2026-10-18T14:00:00Z",
        "load_lb": 42_000,
        "interval_mi": 25,
    }
    for key, value in changes.items():
        if value is ...:
            del values[key]
        else:
            values[key] = value
    return values


def three_routes() -> list[Any]:
    return [
        route(60, 55),
        route(62, 52, origin=destination_point(START, 0.0, 20_000)),
        route(65, 50, origin=destination_point(START, 180.0, 20_000)),
    ]


def post(client: APIClient, body: Any, **extra: Any) -> Any:  # noqa: ANN401
    return client.post("/api/plan", data=json.dumps(body), content_type="application/json", **extra)
