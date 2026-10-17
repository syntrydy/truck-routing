"""Photon geocoding adapter (SPEC sections 2 and 6): the first choice, Nominatim the fallback."""

from planner.infra.http import UpstreamClient
from planner.providers.jsonshape import JsonShape
from planner.providers.places import distinct_places, join_label
from planner.providers.protocols import MAX_RESULTS, Place, PlaceKind, normalize_query

NAME = "photon"
DEFAULT_BASE_URL = "https://photon.komoot.io"
LANGUAGE = "en"
# Photon's coarse `type` mapped to ours. Unknown or missing types are still shown, as a place.
KINDS = {
    "city": PlaceKind.CITY,
    "district": PlaceKind.CITY,
    "locality": PlaceKind.CITY,
    "county": PlaceKind.REGION,
    "state": PlaceKind.REGION,
    "country": PlaceKind.COUNTRY,
    "street": PlaceKind.STREET,
    "house": PlaceKind.ADDRESS,
}

_shape = JsonShape(NAME)


class PhotonGeocoder:
    """Places from a Photon server through the resilient upstream client."""

    name = NAME

    def __init__(self, client: UpstreamClient, base_url: str = DEFAULT_BASE_URL) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    def search(self, query: str) -> tuple[Place, ...]:
        params = {"q": normalize_query(query), "limit": str(MAX_RESULTS), "lang": LANGUAGE}
        payload = self._client.get_json(NAME, f"{self._base_url}/api/", params=params)
        root = _shape.mapping(payload, "response")
        features = _shape.sequence(root.get("features"), "features")
        return distinct_places(_place(feature) for feature in features)


def _place(item: object) -> Place:
    feature = _shape.mapping(item, "feature")
    geometry = _shape.mapping(feature.get("geometry"), "geometry")
    if geometry.get("type") != "Point":
        raise _shape.error("feature geometry is not a Point")
    point = _shape.point(geometry.get("coordinates"))
    properties = _shape.mapping(feature.get("properties"), "properties")

    street, number = (
        _shape.optional_text(properties.get("street"), "street"),
        _shape.optional_text(properties.get("housenumber"), "housenumber"),
    )
    street_line = f"{number} {street}" if street and number else street
    label = join_label(
        [
            _shape.optional_text(properties.get("name"), "name"),
            street_line,
            _shape.optional_text(properties.get("city"), "city"),
            _shape.optional_text(properties.get("state"), "state"),
            _shape.optional_text(properties.get("country"), "country"),
        ]
    )
    if not label:
        raise _shape.error("feature has nothing to label it with")
    kind = KINDS.get(_shape.optional_text(properties.get("type"), "type") or "", PlaceKind.PLACE)
    return Place(label=label, lat=point.lat, lon=point.lon, kind=kind)
