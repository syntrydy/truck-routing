import importlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import respx
from django.core.cache.backends.locmem import LocMemCache
from rest_framework.test import APIClient

from planner.infra.cache import StaleIfErrorCache
from planner.infra.http import ProviderPolicy, UpstreamClient
from planner.infra.jsonlog import JsonFormatter, RequestIdFilter, request_id_var
from planner.infra.metrics import metrics_scope
from tests.infra.fakes import FakeClock, FixedJitter

BACKEND = Path(__file__).resolve().parents[1]
URL = "https://router.project-osrm.org/route"


class TestGzip:
    def test_a_large_response_is_compressed_when_the_client_accepts_it(self) -> None:
        response = APIClient().get(
            "/api/schema/",
            HTTP_ACCEPT="application/vnd.oai.openapi+json",
            HTTP_ACCEPT_ENCODING="gzip",
        )

        assert response["Content-Encoding"] == "gzip"

    def test_nothing_is_compressed_for_a_client_that_does_not_ask(self) -> None:
        response = APIClient().get("/api/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")

        assert "Content-Encoding" not in response


class TestRequestIdInLogs:
    def test_a_log_line_written_while_serving_carries_the_request_id(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        def noisy(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            logging.getLogger("planner.test").warning("inside the request")
            raise ValueError

        monkeypatch.setattr("planner.api.views.get_container", noisy)
        caplog.set_level(logging.WARNING, logger="planner.test")
        seen: list[str] = []

        class Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                RequestIdFilter().filter(record)
                seen.append(JsonFormatter().format(record))

        handler = Capture()
        logging.getLogger("planner.test").addHandler(handler)
        try:
            APIClient().get("/api/ready", HTTP_X_REQUEST_ID="req-42")
        finally:
            logging.getLogger("planner.test").removeHandler(handler)

        assert json.loads(seen[0])["request_id"] == "req-42"

    def test_the_id_is_gone_after_the_request(self) -> None:
        APIClient().get("/api/health", HTTP_X_REQUEST_ID="req-42")

        assert request_id_var.get() == ""

    def test_production_logging_writes_json_to_stdout(self, settings: Any) -> None:
        handler = settings.LOGGING["handlers"]["stdout"]

        assert handler["stream"] == "ext://sys.stdout"
        assert settings.LOGGING["formatters"]["json"]["()"] == "planner.infra.jsonlog.JsonFormatter"
        assert settings.LOGGING["root"]["handlers"] == ["stdout"]


class TestMetricsHooks:
    def client(self, clock: FakeClock) -> UpstreamClient:
        return UpstreamClient(
            [ProviderPolicy("osrm", timeout_s=8.0, max_concurrency=1)],
            ["router.project-osrm.org"],
            "tests/1.0",
            clock=clock,
            sleep=clock.sleep,
            jitter=FixedJitter(1.0),
        )

    def test_a_call_is_timed_including_its_retry_wait(self) -> None:
        clock = FakeClock()
        client = self.client(clock)
        with respx.mock() as api, metrics_scope() as metrics:
            api.get(URL).respond(503)
            with pytest.raises(Exception, match="503"):
                client.get("osrm", URL)

        usage = metrics.upstream["osrm"]
        assert usage.calls == 1
        assert usage.seconds == pytest.approx(0.3)  # the backoff slept on the fake clock

    def test_a_call_rejected_by_an_open_breaker_is_not_counted(self) -> None:
        clock = FakeClock()
        client = self.client(clock)
        with respx.mock() as api:
            api.get(URL).respond(503)
            for _ in range(3):
                with pytest.raises(Exception, match="503"):
                    client.get("osrm", URL)
            with metrics_scope() as metrics, pytest.raises(Exception, match="circuit open"):
                client.get("osrm", URL)

        assert metrics.upstream == {}

    def test_cache_lookups_count_as_hits_and_misses(self) -> None:
        clock = FakeClock(1_000_000.0)
        cache = StaleIfErrorCache(LocMemCache("m", {}), clock)
        with metrics_scope() as metrics:
            for _ in range(3):
                cache.get_or_load("k", lambda: "v", fresh_ttl_s=60, max_stale_age_s=60)

        assert (metrics.cache_hits, metrics.cache_misses) == (2, 1)


class TestGunicornConfig:
    def test_it_loads_with_the_production_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PORT", "9000")
        monkeypatch.setenv("WEB_CONCURRENCY", "3")
        monkeypatch.delenv("GUNICORN_THREADS", raising=False)
        sys.modules.pop("config.gunicorn_conf", None)
        spec = importlib.util.spec_from_file_location(
            "config.gunicorn_conf", BACKEND / "config" / "gunicorn.conf.py"
        )
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert module.bind == "0.0.0.0:9000"  # noqa: S104
        assert module.workers == 3
        assert (module.worker_class, module.threads) == ("gthread", 4)
        assert module.timeout > 20  # longer than a plan's budget
        assert module.accesslog is None
        assert module.logconfig_dict["handlers"]["stdout"]["formatter"] == "json"
        assert "gunicorn.error" in module.logconfig_dict["loggers"]


def test_django_deployment_checks_pass_with_a_production_environment() -> None:
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "DEBUG": "false",
        "ALLOWED_HOSTS": "api.example.com",
        "TRUST_PROXY_SSL_HEADER": "true",
        # Explicit, so that a developer's local .env cannot change what is checked.
        "SECURE_SSL_REDIRECT": "true",
        "SECURE_HSTS_SECONDS": "31536000",
        "SECRET_KEY": "k" * 10 + "".join(chr(c) for c in range(40, 90)),
    }

    result = subprocess.run(  # noqa: S603
        [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "no issues" in result.stdout + result.stderr
