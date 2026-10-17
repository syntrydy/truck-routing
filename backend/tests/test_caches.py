from django.core.cache import caches
from django.core.cache.backends.locmem import LocMemCache
from django.utils.module_loading import import_string

from config.caches import LOCMEM_MAX_ENTRIES, caches_for


def test_without_a_redis_url_the_cache_lives_in_process_memory() -> None:
    config = caches_for("")["default"]

    assert config["BACKEND"] == "django.core.cache.backends.locmem.LocMemCache"
    assert config["OPTIONS"] == {"MAX_ENTRIES": LOCMEM_MAX_ENTRIES}
    assert "LOCATION" not in config


def test_with_a_redis_url_the_cache_uses_redis_with_short_timeouts() -> None:
    config = caches_for("redis://cache.internal:6379/1")["default"]

    assert config["BACKEND"] == "django.core.cache.backends.redis.RedisCache"
    assert config["LOCATION"] == "redis://cache.internal:6379/1"
    assert config["OPTIONS"] == {"socket_connect_timeout": 1, "socket_timeout": 1}


def test_the_redis_backend_can_be_imported() -> None:
    assert import_string(caches_for("redis://localhost:6379/0")["default"]["BACKEND"])


def test_the_default_cache_of_the_project_is_in_process_memory() -> None:
    assert isinstance(caches["default"], LocMemCache)
