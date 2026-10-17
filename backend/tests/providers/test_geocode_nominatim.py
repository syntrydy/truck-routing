import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from planner.infra.errors import (
    UpstreamContractError,
    UpstreamError,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from planner.infra.http import ProviderPolicy, UpstreamClient
from planner.providers.geocode_nominatim import NominatimGeocoder
from planner.providers.protocols import GeocodeProvider, PlaceKind
from tests.infra.fakes import FakeClock, FixedJitter

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "geocode"
HOST = "nominatim.openstreetmap.org"
URL = f"https://{HOST}/search"


def fixture(name: str) -> Any:  # noqa: ANN401
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def client() -> UpstreamClient:
    clock = FakeClock()
    return UpstreamClient(
        [ProviderPolicy("nominatim", timeout_s=4.0, max_concurrency=2)],
        [HOST],
        "tests/1.0",
        clock=clock,
        sleep=clock.sleep,
        jitter=FixedJitter(1.0),
    )


@pytest.fixture
def geocoder(client: UpstreamClient) -> NominatimGeocoder:
    return NominatimGeocoder(client)


def one_result(**changes: Any) -> list[dict[str, Any]]:
    """The first recorded result, with fields replaced (``None`` deletes them).

    ``address`` may be a dict of address-field changes, or any other value to replace it.
    """
    result: dict[str, Any] = fixture("nominatim_city")[0]
    if "address" in changes:
        address = changes.pop("address")
        if isinstance(address, dict):
            for key, value in address.items():
                if value is None:
                    result["address"].pop(key, None)
                else:
                    result["address"][key] = value
        else:
            result["address"] = address
    for key, value in changes.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = value
    return [result]


class TestRecordedResponses:
    def test_maps_a_city_search(self, api: respx.MockRouter, geocoder: NominatimGeocoder) -> None:
        api.get(URL).respond(200, json=fixture("nominatim_city"))

        places = geocoder.search("denver")

        assert [p.label for p in places] == [
            "Denver, Colorado, United States",
            "Denver, Iowa, United States",
            "Denver, Pennsylvania, United States",
            "Denver, Indiana, United States",
        ]

    def test_labels_are_shorter_than_nominatims_display_name(
        self, api: respx.MockRouter, geocoder: NominatimGeocoder
    ) -> None:
        recorded = fixture("nominatim_city")
        api.get(URL).respond(200, json=recorded)

        second = geocoder.search("denver")[1]

        assert "Bremer County" in recorded[1]["display_name"]
        assert "50622" in recorded[1]["display_name"]
        assert second.label == "Denver, Iowa, United States"

    def test_every_label_has_a_region_and_a_country(
        self, api: respx.MockRouter, geocoder: NominatimGeocoder
    ) -> None:
        api.get(URL).respond(200, json=fixture("nominatim_city"))

        for place in geocoder.search("denver"):
            assert place.label.endswith(", United States")
            assert len(place.label.split(", ")) == 3

    def test_coordinates_are_read_from_the_text_fields(
        self, api: respx.MockRouter, geocoder: NominatimGeocoder
    ) -> None:
        api.get(URL).respond(200, json=fixture("nominatim_city"))

        first = geocoder.search("denver")[0]

        assert (first.lat, first.lon) == (39.7392364, -104.984862)

    def test_the_kind_follows_the_address_type(
        self, api: respx.MockRouter, geocoder: NominatimGeocoder
    ) -> None:
        api.get(URL).respond(200, json=fixture("nominatim_city"))

        assert {p.kind for p in geocoder.search("denver")} == {PlaceKind.CITY}

    def test_no_match_is_an_empty_answer(
        self, api: respx.MockRouter, geocoder: NominatimGeocoder
    ) -> None:
        api.get(URL).respond(200, json=fixture("nominatim_empty"))

        assert geocoder.search("qzxwvbnmpl") == ()

    def test_it_satisfies_the_geocode_provider_protocol(self, geocoder: NominatimGeocoder) -> None:
        provider: GeocodeProvider = geocoder

        assert provider.name == "nominatim"


class TestRequest:
    def test_sends_the_cleaned_query_with_the_agreed_options(
        self, api: respx.MockRouter, geocoder: NominatimGeocoder
    ) -> None:
        route = api.get(URL).respond(200, json=fixture("nominatim_empty"))

        geocoder.search("  new   york ")

        assert dict(route.calls.last.request.url.params) == {
            "q": "new york",
            "format": "jsonv2",
            "limit": "8",
            "addressdetails": "1",
            "accept-language": "en",
        }

    @pytest.mark.parametrize("query", ["", "ab", "x" * 101])
    def test_bad_queries_are_refused_before_any_call(
        self, api: respx.MockRouter, geocoder: NominatimGeocoder, query: str
    ) -> None:
        route = api.get(URL).respond(200, json=fixture("nominatim_empty"))

        with pytest.raises(ValueError, match="3 to 100"):
            geocoder.search(query)

        assert not route.called

    def test_a_trailing_slash_in_the_base_url_is_ignored(
        self, api: respx.MockRouter, client: UpstreamClient
    ) -> None:
        route = api.get(URL).respond(200, json=fixture("nominatim_empty"))

        NominatimGeocoder(client, base_url=f"https://{HOST}/").search("denver")

        assert route.calls.last.request.url.path == "/search"


class TestLabelsAndKinds:
    def test_a_place_in_a_town_gets_the_town(
        self, api: respx.MockRouter, geocoder: NominatimGeocoder
    ) -> None:
        body = one_result(
            name="Lakewood Mall",
            address={"city": None, "town": "Lakewood", "state": "Colorado"},
        )
        api.get(URL).respond(200, json=body)

        assert geocoder.search("lakewood mall")[0].label == (
            "Lakewood Mall, Lakewood, Colorado, United States"
        )

    def test_the_county_is_only_used_when_there_is_no_town(
        self, api: respx.MockRouter, geocoder: NominatimGeocoder
    ) -> None:
        body = one_result(
            name="Rocky Trail",
            address={"city": None, "county": "Jefferson County", "state": "Colorado"},
        )
        api.get(URL).respond(200, json=body)

        assert geocoder.search("rocky trail")[0].label == (
            "Rocky Trail, Jefferson County, Colorado, United States"
        )

    def test_a_street_address_has_a_number_and_a_street(
        self, api: respx.MockRouter, geocoder: NominatimGeocoder
    ) -> None:
        body = one_result(
            name="White House",
            addresstype="building",
            address={
                "house_number": "1600",
                "road": "Pennsylvania Avenue Northwest",
                "city": "Washington",
                "state": "District of Columbia",
            },
        )
        api.get(URL).respond(200, json=body)

        place = geocoder.search("white house")[0]

        assert place.label == (
            "White House, 1600 Pennsylvania Avenue Northwest, Washington, "
            "District of Columbia, United States"
        )
        assert place.kind is PlaceKind.ADDRESS

    def test_a_street_result_is_not_repeated(
        self, api: respx.MockRouter, geocoder: NominatimGeocoder
    ) -> None:
        body = one_result(
            name="Pennsylvania Avenue Northwest",
            addresstype="road",
            address={"road": "Pennsylvania Avenue Northwest", "city": "Washington"},
        )
        api.get(URL).respond(200, json=body)

        place = geocoder.search("pennsylvania avenue")[0]

        assert place.label.startswith("Pennsylvania Avenue Northwest, Washington")
        assert place.label.count("Pennsylvania") == 1
        assert place.kind is PlaceKind.STREET

    @pytest.mark.parametrize(
        ("addresstype", "kind"),
        [
            ("city", PlaceKind.CITY),
            ("village", PlaceKind.CITY),
            ("suburb", PlaceKind.CITY),
            ("state", PlaceKind.REGION),
            ("county", PlaceKind.REGION),
            ("country", PlaceKind.COUNTRY),
            ("road", PlaceKind.STREET),
            ("residential", PlaceKind.STREET),
            ("house", PlaceKind.ADDRESS),
            ("building", PlaceKind.ADDRESS),
            ("shop", PlaceKind.PLACE),
            ("something-new", PlaceKind.PLACE),
        ],
    )
    def test_address_types_map_to_kinds(
        self, api: respx.MockRouter, geocoder: NominatimGeocoder, addresstype: str, kind: PlaceKind
    ) -> None:
        api.get(URL).respond(200, json=one_result(addresstype=addresstype))

        assert geocoder.search("denver")[0].kind is kind

    def test_a_missing_address_type_is_still_a_place(
        self, api: respx.MockRouter, geocoder: NominatimGeocoder
    ) -> None:
        api.get(URL).respond(200, json=one_result(addresstype=None))

        assert geocoder.search("denver")[0].kind is PlaceKind.PLACE

    def test_a_region_in_state_form_is_found_under_its_other_names(
        self, api: respx.MockRouter, geocoder: NominatimGeocoder
    ) -> None:
        body = one_result(address={"state": None, "province": "Ontario", "country": "Canada"})
        api.get(URL).respond(200, json=body)

        assert geocoder.search("denver")[0].label == "Denver, Ontario, Canada"

    def test_without_address_parts_the_display_name_is_the_label(
        self, api: respx.MockRouter, geocoder: NominatimGeocoder
    ) -> None:
        body = one_result(name=None, address={})
        body[0]["address"] = {}
        api.get(URL).respond(200, json=body)

        assert geocoder.search("denver")[0].label == body[0]["display_name"]

    def test_repeated_results_are_collapsed(
        self, api: respx.MockRouter, geocoder: NominatimGeocoder
    ) -> None:
        recorded = fixture("nominatim_city")
        api.get(URL).respond(200, json=recorded + recorded)

        assert len(geocoder.search("denver")) == 4

    def test_at_most_eight_places(self, api: respx.MockRouter, geocoder: NominatimGeocoder) -> None:
        results = []
        for number in range(20):
            result = copy.deepcopy(fixture("nominatim_city")[0])
            result["lat"] = str(30.0 + number)
            results.append(result)
        api.get(URL).respond(200, json=results)

        assert len(geocoder.search("denver")) == 8


def broken(**changes: Any) -> list[dict[str, Any]]:
    return one_result(**changes)


MALFORMED: dict[str, Any] = {
    "object": {"error": "x"},
    "text": "none",
    "result-not-an-object": [1],
    "no-address": broken(address=None),
    "address-not-an-object": broken(address=[]),
    "no-latitude": broken(lat=None),
    "text-latitude": broken(lat="north"),
    "boolean-latitude": broken(lat=True),
    "no-longitude": broken(lon=None),
    "latitude-out-of-range": broken(lat="123.4"),
    "longitude-out-of-range": broken(lon="-400"),
    "infinite-latitude": broken(lat="inf"),
    "name-is-a-number": broken(name=5),
    "country-is-a-list": broken(address={"country": ["US"]}),
    "state-is-a-number": broken(address={"state": 5}),
    "type-is-a-number": broken(addresstype=7),
    "nothing-to-label-it": broken(
        name=None,
        display_name=None,
        address={"city": None, "state": None, "country": None, "road": None},
    ),
}


class TestFailures:
    @pytest.mark.parametrize("body", list(MALFORMED.values()), ids=list(MALFORMED))
    def test_unusable_bodies_are_contract_errors(
        self, api: respx.MockRouter, geocoder: NominatimGeocoder, body: Any
    ) -> None:
        api.get(URL).respond(200, json=copy.deepcopy(body))

        with pytest.raises(UpstreamContractError):
            geocoder.search("denver")

    def test_a_reply_that_is_not_json(
        self, api: respx.MockRouter, geocoder: NominatimGeocoder
    ) -> None:
        api.get(URL).respond(200, text="<html>")

        with pytest.raises(UpstreamContractError):
            geocoder.search("denver")

    def test_outages_pass_through(self, api: respx.MockRouter, geocoder: NominatimGeocoder) -> None:
        api.get(URL).respond(503)
        with pytest.raises(UpstreamUnavailable):
            geocoder.search("denver")

        api.get(URL).mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(UpstreamTimeout):
            geocoder.search("denver")

    def test_a_blocked_client_is_an_upstream_error(
        self, api: respx.MockRouter, geocoder: NominatimGeocoder
    ) -> None:
        api.get(URL).respond(403, text="Access blocked")

        with pytest.raises(UpstreamError) as raised:
            geocoder.search("denver")

        assert type(raised.value) is UpstreamError
        assert raised.value.status == 403
