"""Settings for the test suite: hermetic, independent of any local ``.env``."""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")

from config.settings import *  # noqa: E402, F403

SECURE_SSL_REDIRECT = False
# Most tests send many requests from one address; the limiter has its own tests.
RATELIMIT_ENABLE = False
