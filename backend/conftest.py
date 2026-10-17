"""Test bootstrap: provide settings that would otherwise come from the environment."""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("SECURE_SSL_REDIRECT", "false")
