from django.urls import path

from planner.api.views import GeocodeView, HealthView, PlanView, ReadyView

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
    path("ready", ReadyView.as_view(), name="ready"),
    path("geocode", GeocodeView.as_view(), name="geocode"),
    path("plan", PlanView.as_view(), name="plan"),
]
