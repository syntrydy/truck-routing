from django.urls import path

from planner.api.views import HealthView

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
]
