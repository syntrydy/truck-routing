"""Serializers: strict request validation and the shape of the API, for the OpenAPI schema."""

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from planner.domain.models import LatLon, RiskLevel
from planner.infra.resilience import BreakerState
from planner.providers.protocols import MAX_RESULTS, PlaceKind
from planner.services.models import ALLOWED_INTERVALS_MI, PlanBanner, PlanRequest

MAX_LABEL_LENGTH = 200
MAX_LOAD_LB = 200_000
DEFAULT_DEMO_LOAD_LB = 42_000
DEFAULT_DEMO_INTERVAL_MI = 25
PAST_GRACE = timedelta(minutes=15)
MAX_LEAD = timedelta(days=7)


class HealthSerializer(serializers.Serializer[dict[str, str]]):
    """Liveness response."""

    status = serializers.CharField()


PLACE_KINDS = [kind.value for kind in PlaceKind]
BREAKER_STATES = [state.value for state in BreakerState]


class ReadySerializer(serializers.Serializer[Any]):
    """Readiness response."""

    status = serializers.ChoiceField(choices=["ok", "degraded"])
    cache = serializers.BooleanField(help_text="Whether the cache stores and returns a value.")
    providers = serializers.DictField(
        child=serializers.ChoiceField(choices=BREAKER_STATES),
        help_text="Circuit breaker state of each upstream provider.",
    )


class PlaceSerializer(serializers.Serializer[Any]):
    """A place a user can pick."""

    label = serializers.CharField()  # type: ignore[assignment]  # see PointSerializer.label
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    kind = serializers.ChoiceField(choices=PLACE_KINDS)


class GeocodeResponseSerializer(serializers.Serializer[Any]):
    """Places matching a query, best first."""

    results = PlaceSerializer(many=True, help_text=f"At most {MAX_RESULTS}.")


class StrictSerializer(serializers.Serializer[Any]):
    """A serializer that refuses fields it does not know, so typos are not silently ignored."""

    def to_internal_value(self, data: Any) -> Any:  # noqa: ANN401
        if isinstance(data, Mapping):
            unknown = [str(key) for key in data if key not in self.fields]
            if unknown:
                raise serializers.ValidationError({name: ["Unknown field."] for name in unknown})
        return super().to_internal_value(data)


class StrictFloatField(serializers.FloatField):
    """A JSON number. Numeric strings and booleans are not numbers."""

    def to_internal_value(self, data: Any) -> float:  # noqa: ANN401
        if isinstance(data, bool) or not isinstance(data, int | float):
            self.fail("invalid")
        return super().to_internal_value(data)


class StrictCharField(serializers.CharField):
    """A JSON string. Numbers are not silently turned into text."""

    def to_internal_value(self, data: Any) -> str:  # noqa: ANN401
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class StrictIntegerField(serializers.IntegerField):
    """A JSON integer. Strings, booleans and floats (even 5.0) are not integers."""

    default_error_messages = {"invalid": "A whole number is required."}  # noqa: RUF012

    def to_internal_value(self, data: Any) -> int:  # noqa: ANN401
        if not isinstance(data, int):  # DRF's IntegerField itself refuses True and False
            self.fail("invalid")
        return super().to_internal_value(data)


@extend_schema_field({"type": "string", "format": "date-time"})
class OffsetDateTimeField(serializers.Field[datetime, str, str, Any]):
    """An ISO 8601 date and time that states its UTC offset (``Z`` or ``+hh:mm``)."""

    default_error_messages = {  # noqa: RUF012
        "invalid": "Use an ISO 8601 date and time, for example 2026-10-18T06:00:00-05:00.",
        "no_offset": "The time must include a UTC offset, for example 2026-10-18T06:00:00-05:00.",
    }

    def to_internal_value(self, data: Any) -> datetime:  # noqa: ANN401
        if not isinstance(data, str):
            self.fail("invalid")
        try:
            value = datetime.fromisoformat(data)
        except ValueError:
            self.fail("invalid")
        if value.tzinfo is None or value.utcoffset() is None:
            self.fail("no_offset")
        return value

    def to_representation(self, value: datetime) -> str:
        return value.isoformat()


class PointSerializer(StrictSerializer):
    """A place on the map."""

    lat = StrictFloatField(min_value=-90, max_value=90)
    lon = StrictFloatField(min_value=-180, max_value=180)
    # DRF removes declared fields from the class, so "label" does not clash with Field.label
    # at runtime; only the type stubs see a conflict.
    label = StrictCharField(  # type: ignore[assignment]
        max_length=MAX_LABEL_LENGTH, required=False, allow_blank=True, default=""
    )


def _one_of_the_intervals(value: int) -> None:
    if value not in ALLOWED_INTERVALS_MI:
        choices = ", ".join(str(choice) for choice in ALLOWED_INTERVALS_MI)
        raise serializers.ValidationError(f"Must be one of {choices}.")


class PlanRequestSerializer(StrictSerializer):
    """The body of ``POST /api/plan``."""

    origin = PointSerializer()
    destination = PointSerializer()
    departure_at = OffsetDateTimeField()
    load_lb = StrictIntegerField(min_value=0, max_value=MAX_LOAD_LB)
    interval_mi = StrictIntegerField(validators=[_one_of_the_intervals])

    def validate_departure_at(self, value: datetime) -> datetime:
        """The departure must be within [now - 15 min, now + 7 days]; slightly past means now."""
        now: datetime = self.context["now"]
        if value < now - PAST_GRACE:
            raise serializers.ValidationError("The departure time is in the past.")
        if value > now + MAX_LEAD:
            raise serializers.ValidationError("The departure time must be within the next 7 days.")
        return max(value, now)


class DemoQuerySerializer(serializers.Serializer[Any]):
    """The query of ``GET /api/demo``: the trip is fixed, the load and spacing are not."""

    load_lb = serializers.IntegerField(
        min_value=0, max_value=MAX_LOAD_LB, default=DEFAULT_DEMO_LOAD_LB, help_text="Pounds."
    )
    interval_mi = serializers.ChoiceField(
        choices=ALLOWED_INTERVALS_MI, default=DEFAULT_DEMO_INTERVAL_MI, help_text="Miles."
    )


def parse_plan_request(data: Any, now: datetime) -> PlanRequest:  # noqa: ANN401
    """Validate a request body and turn it into a ``PlanRequest``.

    Raises DRF's ``ValidationError`` (which the error handler turns into a 400) for any rule
    broken. ``now`` is passed in so that the departure window is testable.
    """
    serializer = PlanRequestSerializer(data=data, context={"now": now})
    serializer.is_valid(raise_exception=True)
    valid = serializer.validated_data
    return PlanRequest(
        origin=LatLon(valid["origin"]["lat"], valid["origin"]["lon"]),
        destination=LatLon(valid["destination"]["lat"], valid["destination"]["lon"]),
        departure=valid["departure_at"],
        load_lb=valid["load_lb"],
        interval_mi=valid["interval_mi"],
    )


# --- The shape of the response, for the OpenAPI schema. The presenter builds the JSON by hand
# --- (it is compacted), and the tests check that what it builds validates against these.

LEVELS = [level.name for level in RiskLevel]
BANNERS = [banner.value for banner in PlanBanner]


class GeometrySerializer(serializers.Serializer[Any]):
    """A route line as GeoJSON: [longitude, latitude] pairs."""

    type = serializers.ChoiceField(choices=["LineString"])
    coordinates = serializers.ListField(child=serializers.ListField(child=serializers.FloatField()))


class SummarySerializer(serializers.Serializer[Any]):
    """How risky a route is."""

    miles_by_level = serializers.DictField(
        child=serializers.FloatField(),
        help_text="Miles at each known risk level; unknown miles are separate.",
    )
    unknown_miles = serializers.FloatField()
    avg_risk = serializers.FloatField(allow_null=True)
    worst_level = serializers.ChoiceField(choices=LEVELS)
    low_confidence = serializers.BooleanField()


class CheckpointSerializer(serializers.Serializer[Any]):
    """A sampled point on a route with the weather expected when the truck gets there."""

    index = serializers.IntegerField()
    mile = serializers.FloatField()
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    eta = serializers.DateTimeField()
    wind_mph = serializers.FloatField(allow_null=True)
    gust_mph = serializers.FloatField(allow_null=True)
    rain_in_hr = serializers.FloatField(allow_null=True)
    snow_in_hr = serializers.FloatField(allow_null=True)
    level = serializers.ChoiceField(choices=LEVELS)
    reasons = serializers.ListField(child=serializers.CharField())


class RouteSerializer(serializers.Serializer[Any]):
    """One route, ranked."""

    id = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]  # see PointSerializer.label
    rank = serializers.IntegerField()
    distance_mi = serializers.FloatField()
    duration_s = serializers.IntegerField()
    geometry = GeometrySerializer()
    summary = SummarySerializer()
    checkpoints = CheckpointSerializer(many=True)


class HeatmapFrameSerializer(serializers.Serializer[Any]):
    """One hour of the corridor, a value per point (in the order of the points)."""

    risk = serializers.ListField(
        child=serializers.IntegerField(min_value=-1, max_value=4),
        help_text="Risk level 0 (LOW) to 4 (NO_TRAVEL); -1 where the weather is unknown.",
    )
    wind = serializers.ListField(child=serializers.FloatField(allow_null=True))
    rain = serializers.ListField(child=serializers.FloatField(allow_null=True))
    snow = serializers.ListField(child=serializers.FloatField(allow_null=True))


class HeatmapSerializer(serializers.Serializer[Any]):
    """The weather corridor around the routes over the 49 hours from departure."""

    start = serializers.DateTimeField(help_text="Time of the first frame; frames are hourly.")
    points = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField()),
        help_text="[latitude, longitude] pairs.",
    )
    frames = HeatmapFrameSerializer(many=True)


class MetaSerializer(serializers.Serializer[Any]):
    """Where the data came from."""

    routing_source = serializers.CharField()
    weather_source = serializers.CharField()
    weather_stale = serializers.BooleanField()
    generated_at = serializers.DateTimeField()
    request_id = serializers.CharField()


class PlanResponseSerializer(serializers.Serializer[Any]):
    """The response of ``POST /api/plan``."""

    recommended_route_id = serializers.CharField(allow_null=True)
    recommendation_reason = serializers.CharField(allow_null=True)
    banner = serializers.ChoiceField(choices=BANNERS, allow_null=True)
    routes = RouteSerializer(many=True)
    heatmap = HeatmapSerializer()
    notes = serializers.ListField(child=serializers.CharField())
    meta = MetaSerializer()


class ErrorDetailSerializer(serializers.Serializer[Any]):
    """What went wrong."""

    code = serializers.CharField(help_text="A stable code such as VALIDATION or NO_ROUTE.")
    message = serializers.CharField()
    field = serializers.CharField(allow_null=True, help_text="Dotted path of the field at fault.")
    request_id = serializers.CharField()


class ErrorEnvelopeSerializer(serializers.Serializer[Any]):
    """The single shape of every error response."""

    error = ErrorDetailSerializer()
