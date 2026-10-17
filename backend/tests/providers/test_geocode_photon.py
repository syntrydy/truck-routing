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
from planner.providers.geocode_photon import PhotonGeocoder
from planner.providers.protocols import GeocodeProvider, PlaceKind
from tests.infra.fakes import FakeClock, FixedJitter

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "geocode"
HOST = "photon.komoot.io"
URL = f"https://{HOST}/api/"


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
        [ProviderPolicy("photon", timeout_s=4.0, max_concurrency=2)],
        [HOST],
        "tests/1.0",
        clock=clock,
        sleep=clock.sleep,
        jitter=FixedJitter(1.0),
    )


@pytest.fixture
def geocoder(client: UpstreamClient) -> PhotonGeocoder:
    return PhotonGeocoder(client)


class TestRecordedResponses:
    def test_maps_a_city_search(self, api: respx.MockRouter, geocoder: PhotonGeocoder) -> None:
        api.get(URL).respond(200, json=fixture("photon_city"))

        places = geocoder.search("denver")

        assert [p.label for p in places] == [
            "Denver, Colorado, United States",
            "Denver, Iowa, United States",
            "Denver, Pennsylvania, United States",
            "Denver, Indiana, United States",
            "Denver, North Carolina, United States",
            "Denver, King's Lynn and West Norfolk, England, United Kingdom",
            "Denver, Middletown, New York, United States",
            "Denver, Arkansas, United States",
        ]

    def test_labels_include_the_region_and_the_country(
        self, api: respx.MockRouter, geocoder: PhotonGeocoder
    ) -> None:
        api.get(URL).respond(200, json=fixture("photon_city"))

        for place in geocoder.search("denver"):
            assert len(place.label.split(", ")) >= 3  # place, region, country

    def test_coordinates_are_lat_then_lon_from_geojson(
        self, api: respx.MockRouter, geocoder: PhotonGeocoder
    ) -> None:
        api.get(URL).respond(200, json=fixture("photon_city"))

        first = geocoder.search("denver")[0]

        assert (first.lat, first.lon) == (39.7392364, -104.984862)

    def test_kinds_come_from_photons_type(
        self, api: respx.MockRouter, geocoder: PhotonGeocoder
    ) -> None:
        api.get(URL).respond(200, json=fixture("photon_city"))

        places = geocoder.search("denver")

        assert {p.kind for p in places} == {PlaceKind.CITY}

    def test_an_address_search_builds_the_street_line_and_is_an_address(
        self, api: respx.MockRouter, geocoder: PhotonGeocoder
    ) -> None:
        api.get(URL).respond(200, json=fixture("photon_address"))

        places = geocoder.search("1600 pennsylvania ave washington")

        assert places[0].label == (
            "White House, 1600 Pennsylvania Avenue Northwest, Washington, "
            "District of Columbia, United States"
        )
        assert places[0].kind is PlaceKind.ADDRESS

    def test_no_match_is_an_empty_answer(
        self, api: respx.MockRouter, geocoder: PhotonGeocoder
    ) -> None:
        api.get(URL).respond(200, json=fixture("photon_empty"))

        assert geocoder.search("qzxwvbnmpl") == ()

    def test_it_satisfies_the_geocode_provider_protocol(self, geocoder: PhotonGeocoder) -> None:
        provider: GeocodeProvider = geocoder

        assert provider.name == "photon"


class TestRequest:
    def test_sends_the_cleaned_query_with_limit_and_language(
        self, api: respx.MockRouter, geocoder: PhotonGeocoder
    ) -> None:
        route = api.get(URL).respond(200, json=fixture("photon_empty"))

        geocoder.search("  new   york  ")

        assert dict(route.calls.last.request.url.params) == {
            "q": "new york",
            "limit": "8",
            "lang": "en",
        }

    def test_the_query_is_encoded_not_pasted_into_the_url(
        self, api: respx.MockRouter, geocoder: PhotonGeocoder
    ) -> None:
        route = api.get(URL).respond(200, json=fixture("photon_empty"))

        geocoder.search("a&limit=999#b/../c")

        request = route.calls.last.request
        assert request.url.params["q"] == "a&limit=999#b/../c"
        assert request.url.params["limit"] == "8"
        assert request.url.path == "/api/"

    @pytest.mark.parametrize("query", ["", "ab", "x" * 101])
    def test_bad_queries_are_refused_before_any_call(
        self, api: respx.MockRouter, geocoder: PhotonGeocoder, query: str
    ) -> None:
        route = api.get(URL).respond(200, json=fixture("photon_empty"))

        with pytest.raises(ValueError, match="3 to 100"):
            geocoder.search(query)

        assert not route.called

    def test_a_trailing_slash_in_the_base_url_is_ignored(
        self, api: respx.MockRouter, client: UpstreamClient
    ) -> None:
        route = api.get(URL).respond(200, json=fixture("photon_empty"))

        PhotonGeocoder(client, base_url=f"https://{HOST}/").search("denver")

        assert route.calls.last.request.url.path == "/api/"


class TestResultHandling:
    def test_repeated_places_are_collapsed(
        self, api: respx.MockRouter, geocoder: PhotonGeocoder
    ) -> None:
        body = fixture("photon_city")
        body["features"] = body["features"][:2] + body["features"][:2]
        api.get(URL).respond(200, json=body)

        assert len(geocoder.search("denver")) == 2

    def test_at_most_eight_places(self, api: respx.MockRouter, geocoder: PhotonGeocoder) -> None:
        body = fixture("photon_city")
        features = []
        for number in range(20):
            feature = copy.deepcopy(body["features"][0])
            feature["geometry"]["coordinates"][1] += number
            features.append(feature)
        body["features"] = features
        api.get(URL).respond(200, json=body)

        assert len(geocoder.search("denver")) == 8

    def test_an_unknown_type_is_still_a_place(
        self, api: respx.MockRouter, geocoder: PhotonGeocoder
    ) -> None:
        body = fixture("photon_city")
        body["features"] = [body["features"][0]]
        body["features"][0]["properties"]["type"] = "galaxy"
        api.get(URL).respond(200, json=body)

        assert geocoder.search("denver")[0].kind is PlaceKind.PLACE

    def test_a_missing_type_is_still_a_place(
        self, api: respx.MockRouter, geocoder: PhotonGeocoder
    ) -> None:
        body = fixture("photon_city")
        body["features"] = [body["features"][0]]
        del body["features"][0]["properties"]["type"]
        api.get(URL).respond(200, json=body)

        assert geocoder.search("denver")[0].kind is PlaceKind.PLACE

    def test_a_feature_without_a_name_is_labelled_from_its_address(
        self, api: respx.MockRouter, geocoder: PhotonGeocoder
    ) -> None:
        body = fixture("photon_address")
        body["features"] = [body["features"][0]]
        del body["features"][0]["properties"]["name"]
        api.get(URL).respond(200, json=body)

        label = geocoder.search("1600 pennsylvania")[0].label

        assert (
            label
            == "1600 Pennsylvania Avenue Northwest, Washington, District of Columbia, United States"
        )

    def test_a_street_without_a_number_is_labelled_with_the_street(
        self, api: respx.MockRouter, geocoder: PhotonGeocoder
    ) -> None:
        body = fixture("photon_address")
        body["features"] = [body["features"][0]]
        del body["features"][0]["properties"]["housenumber"]
        api.get(URL).respond(200, json=body)

        label = geocoder.search("white house")[0].label

        assert label.startswith("White House, Pennsylvania Avenue Northwest, Washington")

    def test_a_place_that_is_its_own_city_is_not_repeated(
        self, api: respx.MockRouter, geocoder: PhotonGeocoder
    ) -> None:
        body = fixture("photon_city")
        body["features"] = [body["features"][0]]
        body["features"][0]["properties"]["city"] = "Denver"
        api.get(URL).respond(200, json=body)

        assert geocoder.search("denver")[0].label == "Denver, Colorado, United States"


def with_feature(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = fixture("photon_city")
    body["features"] = [body["features"][0]]
    for key, value in changes.items():
        if key == "properties" and value is not None:
            body["features"][0]["properties"].update(value)
        else:
            body["features"][0][key] = value
    return body


MALFORMED: dict[str, Any] = {
    "array": [],
    "no-features": {"type": "FeatureCollection"},
    "features-not-a-list": {"features": {}},
    "feature-not-an-object": {"features": [1]},
    "no-geometry": with_feature(geometry=None),
    "wrong-geometry-type": with_feature(
        geometry={"type": "MultiPoint", "coordinates": [-105.0, 40.0]}
    ),
    "no-coordinates": with_feature(geometry={"type": "Point"}),
    "short-coordinates": with_feature(geometry={"type": "Point", "coordinates": [1.0]}),
    "text-coordinates": with_feature(geometry={"type": "Point", "coordinates": ["a", "b"]}),
    "out-of-range": with_feature(geometry={"type": "Point", "coordinates": [500.0, 10.0]}),
    "no-properties": with_feature(properties=None),
    "text-field-is-a-number": with_feature(properties={"name": 5}),
    "state-is-a-list": with_feature(properties={"state": ["Colorado"]}),
    "type-is-a-number": with_feature(properties={"type": 3}),
    "nothing-to-label-it": with_feature(
        properties={
            "name": None,
            "street": None,
            "city": None,
            "state": None,
            "country": None,
        }
    ),
}


class TestFailures:
    @pytest.mark.parametrize("body", list(MALFORMED.values()), ids=list(MALFORMED))
    def test_unusable_bodies_are_contract_errors(
        self, api: respx.MockRouter, geocoder: PhotonGeocoder, body: Any
    ) -> None:
        api.get(URL).respond(200, json=copy.deepcopy(body))

        with pytest.raises(UpstreamContractError):
            geocoder.search("denver")

    def test_a_reply_that_is_not_json(
        self, api: respx.MockRouter, geocoder: PhotonGeocoder
    ) -> None:
        api.get(URL).respond(200, text="<html>")

        with pytest.raises(UpstreamContractError):
            geocoder.search("denver")

    def test_outages_pass_through(self, api: respx.MockRouter, geocoder: PhotonGeocoder) -> None:
        api.get(URL).respond(503)
        with pytest.raises(UpstreamUnavailable):
            geocoder.search("denver")

        api.get(URL).mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(UpstreamTimeout):
            geocoder.search("denver")

    def test_a_rejected_request_is_an_upstream_error(
        self, api: respx.MockRouter, geocoder: PhotonGeocoder
    ) -> None:
        api.get(URL).respond(400, json={"message": "bad"})

        with pytest.raises(UpstreamError) as raised:
            geocoder.search("denver")

        assert type(raised.value) is UpstreamError
