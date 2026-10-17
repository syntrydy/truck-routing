"""Root URL configuration."""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

urlpatterns = [
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/", include("planner.api.urls")),
]

handler404 = "planner.api.errors.json_not_found"
handler500 = "planner.api.errors.json_server_error"
