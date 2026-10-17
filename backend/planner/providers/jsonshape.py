"""Strict reading of provider JSON.

Provider responses are untrusted input: every value is checked before it is used, and
anything unexpected becomes an ``UpstreamContractError`` naming the provider.
"""

import math
from collections.abc import Mapping, Sequence
from typing import Any

from planner.domain.models import LatLon
from planner.infra.errors import UpstreamContractError

POINT_SIZE = 2  # [lon, lat]; some providers append an altitude, which is ignored


class JsonShape:
    """Validating accessors that report problems as the given provider's contract errors."""

    def __init__(self, provider: str) -> None:
        self._provider = provider

    def error(self, message: str) -> UpstreamContractError:
        return UpstreamContractError(self._provider, message)

    def mapping(self, value: object, what: str) -> Mapping[str, Any]:
        if not isinstance(value, dict):
            raise self.error(f"{what} is not an object")
        return value

    def sequence(self, value: object, what: str) -> Sequence[Any]:
        if not isinstance(value, list):
            raise self.error(f"{what} is not a list")
        return value

    def number(self, value: object, what: str, *, allow_negative: bool = False) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
        ):
            raise self.error(f"{what} is not a finite number")
        if value < 0 and not allow_negative:
            raise self.error(f"{what} is negative")
        return float(value)

    def optional_number(self, value: object, what: str) -> float | None:
        """A finite non-negative number, or ``None`` where the provider has no value."""
        return None if value is None else self.number(value, what)

    def integer(self, value: object, what: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise self.error(f"{what} is not a whole number")
        return value

    def optional_integer(self, value: object, what: str) -> int | None:
        return None if value is None else self.integer(value, what)

    def optional_text(self, value: object, what: str) -> str | None:
        """A trimmed non-empty string, or ``None`` when the provider left the field out."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise self.error(f"{what} is not text")
        return value.strip() or None

    def numbers(self, value: object, what: str) -> list[float]:
        return [self.number(item, what) for item in self.sequence(value, what)]

    def point(self, coordinate: object) -> LatLon:
        """A GeoJSON ``[lon, lat]`` position."""
        values = self.sequence(coordinate, "coordinate")
        if len(values) < POINT_SIZE:
            raise self.error("coordinate has fewer than two values")
        lon = self.number(values[0], "longitude", allow_negative=True)
        lat = self.number(values[1], "latitude", allow_negative=True)
        try:
            return LatLon(lat, lon)
        except ValueError as error:
            raise self.error(f"coordinate out of range: {error}") from error
