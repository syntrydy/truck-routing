"""Nominatim geocoding adapter, the fallback behind Photon (SPEC sections 2 and 6).

The public Nominatim server asks for an identifying User-Agent, at most one request per second
and no autocomplete use; the client enforces the first two (see ``MinSpacing``) and this
adapter is only ever called for a finished search, never while the user types.
"""

from planner.infra.http import UpstreamClient
from planner.providers.jsonshape import JsonShape
from planner.providers.places import distinct_places, join_label
from planner.providers.protocols import MAX_RESULTS, Place, PlaceKind, normalize_query

NAME = "nominatim"
DEFAULT_BASE_URL = "https://nominatim.openstreetmap.org"
LANGUAGE = "en"
# The address fields that name the town a place is in, most specific first.
LOCALITY_FIELDS = ("city", "town", "village", "hamlet", "municipality", "suburb", "county")
REGION_FIELDS = ("state", "region", "province")
KINDS = {
    **dict.fromkeys(
        (
            "city",
            "town",
            "village",
            "hamlet",
            "suburb",
            "municipality",
            "city_district",
            "quarter",
            "neighbourhood",
            "locality",
        ),
        PlaceKind.CITY,
    ),
    **dict.fromkeys(("state", "county", "region", "province", "state_district"), PlaceKind.REGION),
    "country": PlaceKind.COUNTRY,
    **dict.fromkeys(("road", "street", "residential"), PlaceKind.STREET),
    **dict.fromkeys(("house", "building", "apartments"), PlaceKind.ADDRESS),
}

_shape = JsonShape(NAME)


class NominatimGeocoder:
    """Places from a Nominatim server through the resilient upstream client."""

    name = NAME

    def __init__(self, client: UpstreamClient, base_url: str = DEFAULT_BASE_URL) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    def search(self, query: str) -> tuple[Place, ...]:
        params = {
            "q": normalize_query(query),
            "format": "jsonv2",
            "limit": str(MAX_RESULTS),
            "addressdetails": "1",
            "accept-language": LANGUAGE,
        }
        payload = self._client.get_json(NAME, f"{self._base_url}/search", params=params)
        return distinct_places(_place(item) for item in _shape.sequence(payload, "response"))


def _place(item: object) -> Place:
    entry = _shape.mapping(item, "result")
    address = _shape.mapping(entry.get("address"), "address")

    name = _shape.optional_text(entry.get("name"), "name")
    road = _shape.optional_text(address.get("road"), "road")
    number = _shape.optional_text(address.get("house_number"), "house_number")
    label = join_label(
        [
            name,
            f"{number} {road}" if road and number else road,
            _first_text(address, LOCALITY_FIELDS),
            _first_text(address, REGION_FIELDS),
            _shape.optional_text(address.get("country"), "country"),
        ]
    ) or (_shape.optional_text(entry.get("display_name"), "display_name") or "")
    if not label:
        raise _shape.error("result has nothing to label it with")

    point = _shape.position(entry.get("lat"), entry.get("lon"))
    kind_name = _shape.optional_text(entry.get("addresstype"), "addresstype")
    return Place(
        label=label,
        lat=point.lat,
        lon=point.lon,
        kind=KINDS.get(kind_name or "", PlaceKind.PLACE),
    )


def _first_text(address: object, fields: tuple[str, ...]) -> str | None:
    """The first of ``fields`` that the address has."""
    mapping = _shape.mapping(address, "address")
    for field in fields:
        value = _shape.optional_text(mapping.get(field), field)
        if value:
            return value
    return None
