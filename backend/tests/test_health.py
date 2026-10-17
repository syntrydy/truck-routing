from rest_framework.test import APIClient


def test_health_returns_ok() -> None:
    response = APIClient().get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_schema_includes_health() -> None:
    response = APIClient().get("/api/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")

    assert response.status_code == 200
    assert "/api/health" in response.json()["paths"]
