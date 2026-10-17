"""Django settings, fully driven by environment variables.

Every variable read here is documented in ``backend/.env.example``. A local
``backend/.env`` file is loaded when present; real environment variables win.
"""

from pathlib import Path

import environ

from config.caches import caches_for

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

DEBUG = env.bool("DEBUG", default=False)

# A key is only optional in development; production must provide its own.
SECRET_KEY = env("SECRET_KEY", default="insecure-dev-key" if DEBUG else environ.Env.NOTSET)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
# Headers the frontend may read: the request ID for support, Retry-After after a 429.
CORS_EXPOSE_HEADERS = ["X-Request-ID", "Retry-After"]
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Disposable cache shared by the API workers: in-process memory unless REDIS_URL is set.
CACHES = caches_for(env("REDIS_URL", default=""))

# Outbound calls to upstream providers (SPEC sections 6 and 8): only these hosts, over https.
UPSTREAM_USER_AGENT = env(
    "UPSTREAM_USER_AGENT",
    default="WeatherAwareTruckRouting/0.1 (+https://github.com/syntrydy/truck-routing)",
)
UPSTREAM_ALLOWED_HOSTS = env.list(
    "UPSTREAM_ALLOWED_HOSTS",
    default=[
        "router.project-osrm.org",
        "api.openrouteservice.org",
        "api.open-meteo.com",
        "photon.komoot.io",
        "nominatim.openstreetmap.org",
    ],
)

# Optional openrouteservice key. When set, openrouteservice is the routing fallback behind OSRM.
# It is a secret: keep it in the environment, never in the repository.
ORS_API_KEY = env("ORS_API_KEY", default="")

# Per-client rate limits, counted in the cache (SPEC section 6). With per-process memory
# (no REDIS_URL) each worker counts separately, so the effective limit is higher.
RATELIMIT_ENABLE = env.bool("RATE_LIMIT_ENABLED", default=True)
RATELIMIT_USE_CACHE = "default"
RATELIMIT_IP_META_KEY = "planner.api.ratelimit.client_ip"
PLAN_RATE_LIMIT = env("PLAN_RATE_LIMIT", default="10/m")
GEOCODE_RATE_LIMIT = env("GEOCODE_RATE_LIMIT", default="60/m")
# How many reverse proxies sit in front of the API and append to X-Forwarded-For (Render: 1).
# Leave 0 when clients connect directly: the header is then ignored, as anyone can forge it.
TRUSTED_PROXY_COUNT = env.int("TRUSTED_PROXY_COUNT", default=0)

# Trip planning (SPEC sections 4.2 and 4.5).
TRUCK_MAX_SPEED_MPH = env.float("TRUCK_MAX_SPEED_MPH", default=65.0)
# Which wind drives risk and the load rules: "sustained" (the brief's table) or "gust".
RISK_WIND_BASIS = env("RISK_WIND_BASIS", default="sustained")

# The API is stateless: no database, sessions or auth apps.
DATABASES: dict[str, dict[str, str]] = {}

INSTALLED_APPS = [
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "planner",
]

MIDDLEWARE = [
    "planner.api.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Security headers and transport settings (SPEC section 8).
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=not DEBUG)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0 if DEBUG else 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
if env.bool("TRUST_PROXY_SSL_HEADER", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "planner.api.errors.api_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Weather-Aware Truck Routing API",
    "DESCRIPTION": "Safest-route planning for trucks based on weather along the route.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # One name for each choice list that several fields share.
    "ENUM_NAME_OVERRIDES": {
        "RiskLevelEnum": "planner.api.serializers.LEVELS",
        "BannerEnum": "planner.api.serializers.BANNERS",
    },
}
