import pytest

from planner.providers.places import distinct_places, join_label
from planner.providers.protocols import MAX_RESULTS, Place, PlaceKind, normalize_query


def place(label: str, lat: float = 40.0, lon: float = -105.0) -> Place:
    return Place(label=label, lat=lat, lon=lon, kind=PlaceKind.CITY)


class TestJoinLabel:
    def test_joins_the_parts_with_commas(self) -> None:
        assert (
            join_label(["Denver", "Colorado", "United States"]) == "Denver, Colorado, United States"
        )

    def test_leaves_out_missing_and_blank_parts(self) -> None:
        assert join_label([None, "Denver", "", "Colorado", None]) == "Denver, Colorado"

    def test_a_part_that_repeats_the_previous_one_is_dropped(self) -> None:
        assert join_label(["Denver", "denver", "Colorado"]) == "Denver, Colorado"

    def test_the_same_word_further_apart_is_kept(self) -> None:
        assert join_label(["Washington", "District of Columbia", "Washington"]) == (
            "Washington, District of Columbia, Washington"
        )

    def test_nothing_gives_an_empty_label(self) -> None:
        assert join_label([None, ""]) == ""


class TestDistinctPlaces:
    def test_keeps_the_order(self) -> None:
        assert distinct_places([place("B"), place("A")]) == (place("B"), place("A"))

    def test_drops_the_same_label_at_the_same_spot(self) -> None:
        places = [place("Denver"), place("DENVER", 40.0001, -105.0001), place("Boulder")]

        assert [p.label for p in distinct_places(places)] == ["Denver", "Boulder"]

    def test_keeps_the_same_label_in_different_places(self) -> None:
        places = [place("Denver", 39.7, -105.0), place("Denver", 42.7, -92.3)]

        assert len(distinct_places(places)) == 2

    def test_keeps_different_labels_at_the_same_spot(self) -> None:
        assert len(distinct_places([place("Denver"), place("Mile High City")])) == 2

    def test_stops_at_the_maximum(self) -> None:
        places = [place(f"Place {n}", 40.0 + n) for n in range(MAX_RESULTS + 5)]

        assert len(distinct_places(places)) == MAX_RESULTS

    def test_the_maximum_counts_distinct_places_only(self) -> None:
        places = [place("Same")] * 20 + [place(f"Other {n}", 41.0 + n) for n in range(10)]

        result = distinct_places(places)

        assert len(result) == MAX_RESULTS
        assert result[0].label == "Same"

    def test_accepts_any_iterable(self) -> None:
        assert distinct_places(place(label) for label in ["A", "B"]) == (place("A"), place("B"))


class TestPlace:
    def test_holds_its_values(self) -> None:
        item = Place("Denver, Colorado, United States", 39.7, -105.0, PlaceKind.CITY)

        assert (item.lat, item.lon, item.kind) == (39.7, -105.0, PlaceKind.CITY)

    @pytest.mark.parametrize(("lat", "lon"), [(91.0, 0.0), (0.0, 181.0)])
    def test_rejects_coordinates_out_of_range(self, lat: float, lon: float) -> None:
        with pytest.raises(ValueError, match="outside"):
            Place("x", lat, lon, PlaceKind.PLACE)

    def test_rejects_an_empty_label(self) -> None:
        with pytest.raises(ValueError, match="label"):
            Place("", 0.0, 0.0, PlaceKind.PLACE)

    def test_kinds_are_plain_strings_for_the_api(self) -> None:
        assert PlaceKind.CITY.value == "city"
        assert {kind.value for kind in PlaceKind} == {
            "city",
            "region",
            "country",
            "street",
            "address",
            "place",
        }


class TestNormalizeQuery:
    def test_collapses_whitespace(self) -> None:
        assert normalize_query("  New \t York\n City ") == "New York City"

    def test_three_characters_is_enough(self) -> None:
        assert normalize_query("abc") == "abc"

    def test_the_length_is_counted_after_cleaning(self) -> None:
        assert normalize_query(" a   b ") == "a b"  # exactly three characters

    def test_a_hundred_characters_is_allowed(self) -> None:
        assert normalize_query("a" * 100) == "a" * 100

    @pytest.mark.parametrize("query", ["", "  ", "ab", " a ", "a" * 101])
    def test_rejects_queries_outside_three_to_a_hundred_characters(self, query: str) -> None:
        with pytest.raises(ValueError, match="3 to 100"):
            normalize_query(query)

    def test_the_length_limit_applies_after_cleaning(self) -> None:
        assert normalize_query("a" + " " * 200 + "b" * 5) == "a bbbbb"
