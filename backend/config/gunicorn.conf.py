"""Gunicorn settings for production (SPEC section 10). Every value can be set in the environment."""

import os

from config.settings import LOGGING

# A plan can take up to its 20 s budget, plus time to build the response.
PLAN_BUDGET_MARGIN_S = 10

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"  # noqa: S104 - the platform's proxy connects to it
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
# Threads, not more workers: the plan service waits on the network, and the upstream client
# is thread-safe and shares its circuit breakers and rate gates across the threads.
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
timeout = 20 + PLAN_BUDGET_MARGIN_S
graceful_timeout = timeout
keepalive = 5
worker_tmp_dir = "/dev/shm"  # noqa: S108  # nosec B108 - heartbeat files in memory, as gunicorn advises

# The same JSON logs as the application. Requests are not logged line by line: the plan
# record and the error handler already say what matters.
accesslog = None
logconfig_dict = {**LOGGING, "loggers": {"gunicorn.error": {"level": "INFO", "propagate": True}}}
