"""An HTTP client that answers from the recorded upstream responses (``PROVIDERS_MODE=fixtures``).

The real adapters run unchanged; only the network is replaced. It serves the end-to-end test
and local demos without internet. Routing always returns the recorded Boulder to Fort Collins
routes, whatever the places asked for; weather is the recorded series moved to the days
asked for, so the forecast always covers the trip.
"""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

OSRM_HOST = "router.project-osrm.org"
OPEN_METEO_HOST = "api.open-meteo.com"
PHOTON_HOST = "photon.komoot.io"
SECONDS_PER_HOUR = 3600
HOURS_PER_DAY = 24
BAD_REQUEST = 400
OK = 200

# Places the recorded geocoder answers for, with the coordinates of the recorded routes' ends.
# Each is (words to look for in the query, name, state, longitude, latitude).
_PLACES = (
    ("boulder", "Boulder", "Colorado", -105.2705, 40.0150),
    ("fort", "Fort Collins", "Colorado", -105.0844, 40.5853),
)


class UnrecordedRequest(RuntimeError):  # noqa: N818 - a programming error, not an upstream failure
    """Something asked for a host or path that fixture mode has no recording for."""


class FixtureUpstream:
    """Serves the recorded OSRM, Open-Meteo and Photon responses from ``fixtures_dir``."""

    def __init__(self, fixtures_dir: Path) -> None:
        self._dir = fixtures_dir

    def client(self) -> httpx.Client:
        """An ``httpx.Client`` whose transport is this object, never the network."""
        return httpx.Client(transport=httpx.MockTransport(self.handle), follow_redirects=False)

    def handle(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == OSRM_HOST:
            return self._osrm(request)
        if host == OPEN_METEO_HOST:
            return self._open_meteo(request)
        if host == PHOTON_HOST:
            return self._photon(request)
        msg = f"fixture mode has no recording for {host}"
        raise UnrecordedRequest(msg)

    def _load(self, name: str) -> Any:  # noqa: ANN401 - recorded JSON of any shape
        return json.loads((self._dir / name).read_text())

    def _osrm(self, request: httpx.Request) -> httpx.Response:
        waypoints = request.url.path.rsplit("/", 1)[-1].count(";") + 1
        if waypoints > 2:  # noqa: PLR2004 - a detour via a point: the recorded server had none
            return httpx.Response(BAD_REQUEST, json=self._load("osrm/no_route.json"))
        return httpx.Response(OK, json=self._load("osrm/two_routes.json"))

    def _open_meteo(self, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        count = len(params["latitude"].split(","))
        first = date.fromisoformat(params["start_date"])
        last = date.fromisoformat(params["end_date"])
        places = [_weather_for_days(self._load("openmeteo/single_point.json"), first, last)] * count
        return httpx.Response(OK, json=places if count > 1 else places[0])

    def _photon(self, request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("q", "").lower()
        features = [
            {
                "type": "Feature",
                "properties": {
                    "osm_key": "place",
                    "osm_value": "city",
                    "type": "city",
                    "name": name,
                    "state": state,
                    "country": "United States",
                },
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            }
            for needle, name, state, lon, lat in _PLACES
            if needle in query
        ]
        return httpx.Response(OK, json={"type": "FeatureCollection", "features": features})


def _weather_for_days(recorded: dict[str, Any], first: date, last: date) -> dict[str, Any]:
    """The recorded series repeated to cover the UTC days ``first`` to ``last``."""
    start = int(datetime(first.year, first.month, first.day, tzinfo=UTC).timestamp())
    hours = ((last - first) + timedelta(days=1)).days * HOURS_PER_DAY
    hourly: dict[str, Any] = recorded["hourly"]
    shifted = {
        name: [values[hour % len(values)] for hour in range(hours)]
        for name, values in hourly.items()
        if name != "time"
    }
    shifted["time"] = [start + hour * SECONDS_PER_HOUR for hour in range(hours)]
    return {**recorded, "hourly": shifted}
