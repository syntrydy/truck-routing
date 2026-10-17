"""Serializers for the public API."""

from rest_framework import serializers


class HealthSerializer(serializers.Serializer[dict[str, str]]):
    """Liveness response."""

    status = serializers.CharField()
