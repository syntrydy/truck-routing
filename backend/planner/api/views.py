"""API views."""

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from planner.api.serializers import HealthSerializer


class HealthView(APIView):
    """Liveness probe. Makes no upstream calls."""

    @extend_schema(responses=HealthSerializer, operation_id="health")
    def get(self, request: Request) -> Response:
        return Response({"status": "ok"})
