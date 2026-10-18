from django.urls import path

from planner.api.views import DemoView, GeocodeView, HealthView, PlanView, ReadyView

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
    path("ready", ReadyView.as_view(), name="ready"),
    path("geocode", GeocodeView.as_view(), name="geocode"),
    path("demo", DemoView.as_view(), name="demo"),
    path("plan", PlanView.as_view(), name="plan"),
]
