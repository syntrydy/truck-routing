"""Building and tidying `Place` results, shared by the geocoding adapters."""

from collections.abc import Iterable

from planner.providers.protocols import MAX_RESULTS, Place

COORDINATE_DECIMALS = 3  # about 100 m: places closer than this with the same label are one


def join_label(parts: Iterable[str | None]) -> str:
    """Comma-join the non-empty parts, leaving out a part that repeats the one before it."""
    kept: list[str] = []
    for part in parts:
        if part and (not kept or kept[-1].casefold() != part.casefold()):
            kept.append(part)
    return ", ".join(kept)


def distinct_places(places: Iterable[Place]) -> tuple[Place, ...]:
    """The first ``MAX_RESULTS`` places, skipping repeats of the same label and spot."""
    seen: set[tuple[str, float, float]] = set()
    result: list[Place] = []
    for place in places:
        key = (
            place.label.casefold(),
            round(place.lat, COORDINATE_DECIMALS),
            round(place.lon, COORDINATE_DECIMALS),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(place)
        if len(result) == MAX_RESULTS:
            break
    return tuple(result)
