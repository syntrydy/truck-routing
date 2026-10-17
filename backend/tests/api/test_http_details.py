from datetime import UTC, datetime, timedelta
from typing import Any

from rest_framework.test import APIClient

from planner.api.views import utc_now


def test_utc_now_is_the_current_time_in_utc() -> None:
    before = datetime.now(UTC)

    now = utc_now()

    assert now.tzinfo is UTC
    assert before <= now <= before + timedelta(seconds=5)


def test_a_browser_may_read_the_request_id_and_retry_after(settings: Any) -> None:
    settings.CORS_ALLOWED_ORIGINS = ["https://app.example"]

    response = APIClient().get("/api/health", headers={"Origin": "https://app.example"})

    assert response["Access-Control-Allow-Origin"] == "https://app.example"
    exposed = {name.strip() for name in response["Access-Control-Expose-Headers"].split(",")}
    assert exposed == {"X-Request-ID", "Retry-After"}


def test_other_origins_get_no_cors_headers(settings: Any) -> None:
    settings.CORS_ALLOWED_ORIGINS = ["https://app.example"]

    response = APIClient().get("/api/health", headers={"Origin": "https://evil.example"})

    assert "Access-Control-Allow-Origin" not in response
