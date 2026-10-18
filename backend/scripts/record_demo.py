"""Record the stormy demo corridor from OSRM and the Open-Meteo historical forecast archive.

Run once, from ``backend``: ``uv run python scripts/record_demo.py``. It writes the two files in
``fixtures/demo`` that demo mode replays (see the README there). The network is used only here.
"""

import json
from pathlib import Path

import httpx

from planner.domain.geometry import METERS_PER_MILE, haversine_m
from planner.domain.models import LatLon

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "demo"
OSRM = "https://router.project-osrm.org/route/v1/driving"
ARCHIVE = "https://historical-forecast-api.open-meteo.com/v1/forecast"
DENVER = LatLon(39.7392, -104.9903)
SALT_LAKE_CITY = LatLon(40.7608, -111.8910)
# Waypoints that make OSRM take other roads than I-80 through Wyoming.
VIAS = {
    "I-70 through Grand Junction": LatLon(39.0639, -108.5506),
    "US-40 through Craig": LatLon(40.5185, -107.5464),
}
KEEP_EVERY_MI = 2.0  # route points are thinned to about this spacing
ANCHOR_EVERY_MI = 45.0  # weather is recorded at about this spacing along the routes
FIRST_DAY, LAST_DAY = "2024-01-15", "2024-01-20"
HOURLY = "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall,weather_code"
TIMEOUT_S = 60


def fetch_routes() -> list[dict[str, object]]:
    routes: list[dict[str, object]] = []
    for name, via in [("I-80 through Wyoming", None), *VIAS.items()]:
        stops = [DENVER, SALT_LAKE_CITY] if via is None else [DENVER, via, SALT_LAKE_CITY]
        path = ";".join(f"{p.lon:.6f},{p.lat:.6f}" for p in stops)
        params = {"overview": "full", "geometries": "geojson", "steps": "false"}
        response = httpx.get(f"{OSRM}/{path}", params=params, timeout=TIMEOUT_S)
        response.raise_for_status()
        route = response.json()["routes"][0]
        routes.append(
            {
                "name": name,
                "distance_m": round(route["distance"], 1),
                "duration_s": round(route["duration"], 1),
                "points": thinned(route["geometry"]["coordinates"]),
            }
        )
    return routes


def thinned(coordinates: list[list[float]]) -> list[list[float]]:
    """``[lon, lat]`` pairs, keeping the ends and a point about every ``KEEP_EVERY_MI``."""
    kept = [coordinates[0]]
    for lon, lat in coordinates[1:-1]:
        last = kept[-1]
        gap = haversine_m(LatLon(last[1], last[0]), LatLon(lat, lon))
        if gap >= KEEP_EVERY_MI * METERS_PER_MILE:
            kept.append([lon, lat])
    kept.append(coordinates[-1])
    return [[round(lon, 4), round(lat, 4)] for lon, lat in kept]


def anchors(routes: list[dict[str, object]]) -> list[LatLon]:
    """Places along every route, each at least ``ANCHOR_EVERY_MI`` from the ones before it."""
    chosen: list[LatLon] = []
    for route in routes:
        points = route["points"]
        assert isinstance(points, list)  # noqa: S101 - a script, shaped by fetch_routes
        for lon, lat in points:
            place = LatLon(round(lat, 1), round(lon, 1))
            nearest = min((haversine_m(place, other) for other in chosen), default=None)
            if nearest is None or nearest >= ANCHOR_EVERY_MI * METERS_PER_MILE:
                chosen.append(place)
    return chosen


def fetch_weather(places: list[LatLon]) -> list[dict[str, object]]:
    params = {
        "latitude": ",".join(f"{p.lat:.1f}" for p in places),
        "longitude": ",".join(f"{p.lon:.1f}" for p in places),
        "hourly": HOURLY,
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timeformat": "unixtime",
        "timezone": "GMT",
        "start_date": FIRST_DAY,
        "end_date": LAST_DAY,
    }
    response = httpx.get(ARCHIVE, params=params, timeout=TIMEOUT_S)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else [payload]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    routes = fetch_routes()
    places = anchors(routes)
    weather = fetch_weather(places)
    (OUT / "denver_salt_lake_routes.json").write_text(
        json.dumps({"routes": routes}, separators=(",", ":")) + "\n"
    )
    (OUT / "denver_salt_lake_weather.json").write_text(
        json.dumps(
            {
                "first_day": FIRST_DAY,
                "last_day": LAST_DAY,
                "places": [
                    {
                        "lat": entry["latitude"],
                        "lon": entry["longitude"],
                        "units": entry["hourly_units"],
                        "hourly": entry["hourly"],
                    }
                    for entry in weather
                ],
            },
            separators=(",", ":"),
        )
        + "\n"
    )
    print(f"{len(routes)} routes, {len(places)} weather places")  # noqa: T201


if __name__ == "__main__":
    main()
