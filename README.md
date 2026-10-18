# Weather-Aware Truck Routing

A web app that recommends the safest truck route between two places, based on the weather along the route at the estimated arrival time, the load weight and the travel time.

## Features

_To be filled in._

## Architecture

_To be filled in. See [`docs/SPEC.md`](docs/SPEC.md) for the technical specification._

## Getting started

_To be filled in._

## Configuration

The backend reads its settings from environment variables (`backend/.env` in development). Defaults are safe for development; production sets the ones marked **required**.

| Variable                                                      | Default                      | Meaning                                                                                          |
| ------------------------------------------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------ |
| `DEBUG`                                                       | `false`                      | Development mode. Never on in production.                                                        |
| `SECRET_KEY`                                                  | none                         | **Required** unless `DEBUG` is on.                                                               |
| `ALLOWED_HOSTS`                                               | `localhost,127.0.0.1`        | **Required** in production: the API's host name.                                                 |
| `CORS_ALLOWED_ORIGINS`                                        | none                         | **Required** in production: the exact web origin, e.g. `https://truck-routing-web.vercel.app`.   |
| `CSRF_TRUSTED_ORIGINS`                                        | none                         | The same origin.                                                                                 |
| `TRUST_PROXY_SSL_HEADER`                                      | `false`                      | `true` behind a proxy that sets `X-Forwarded-Proto` (Render).                                    |
| `TRUSTED_PROXY_COUNT`                                         | `0`                          | Proxies in front of the API that append to `X-Forwarded-For` (Render: `1`).                      |
| `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`                  | on / one year unless `DEBUG` | Transport security.                                                                              |
| `REDIS_URL`                                                   | empty                        | Shared cache and rate limits; without it each worker keeps its own in memory.                    |
| `ORS_API_KEY`                                                 | empty                        | Optional openrouteservice key, the routing fallback behind OSRM. A secret.                       |
| `PLAN_RATE_LIMIT`, `GEOCODE_RATE_LIMIT`, `RATE_LIMIT_ENABLED` | `10/m`, `60/m`, `true`       | Per-client limits.                                                                               |
| `TRUCK_MAX_SPEED_MPH`, `RISK_WIND_BASIS`                      | `65`, `sustained`            | Planning assumptions (SPEC section 4).                                                           |
| `UPSTREAM_USER_AGENT`, `UPSTREAM_ALLOWED_HOSTS`               | see settings                 | Identification and the allowlist for outbound requests.                                          |
| `PROVIDERS_MODE`, `ALLOW_FIXTURE_PROVIDERS`                   | `live`, `false`              | `fixtures` answers from recorded responses (tests, demos); refused in production unless allowed. |
| `LOG_LEVEL`                                                   | `INFO`                       | JSON logs on stdout.                                                                             |
| `PORT`, `WEB_CONCURRENCY`, `GUNICORN_THREADS`                 | `8000`, `2`, `4`             | Read by `config/gunicorn.conf.py`.                                                               |

The frontend reads two build-time variables: `VITE_API_BASE_URL` (the API's origin; empty means the same origin, which the development proxy uses) and `VITE_MAP_STYLE_URL` (a different basemap style).

## Development

Prerequisites: git, [uv](https://docs.astral.sh/uv/), Node 20+, make and [pre-commit](https://pre-commit.com/).

```bash
make check             # everything CI runs (backend and frontend)
make be-test ARGS="-k health"   # focused backend tests
pre-commit install     # run the hooks on every commit
pre-commit run --all-files
```

The hooks run ruff, mypy, prettier, eslint and gitleaks, plus basic file hygiene checks. ruff, mypy, prettier and eslint come from the project lockfiles, so hook results match CI.

The backend reads its settings from the environment; for local development copy `backend/.env.example` to `backend/.env`.

## Testing

_To be filled in._

## Deployment

The API runs on [Render](https://render.com) (free web service) and the web app on [Vercel](https://vercel.com). Both are configured in the repository: `render.yaml` and `frontend/vercel.json`.

1. **API.** In Render choose New, Blueprint and pick this repository. Render creates `truck-routing-api` from `render.yaml`, generates `SECRET_KEY` and asks for the values marked `sync: false`. Leave `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` for step 3; add `ORS_API_KEY` if you have one. If your service gets a different host name than `truck-routing-api-dw0w.onrender.com`, set `ALLOWED_HOSTS` to it.
2. **Web app.** In Vercel import the repository and set the root directory to `frontend`. Add `VITE_API_BASE_URL` = the API's origin (`https://truck-routing-api-dw0w.onrender.com`) and deploy. The Content Security Policy in `frontend/vercel.json` names the API origin; change it there if the host name differs.
3. **Connect them.** Set `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` on the API to the exact Vercel origin (no trailing slash) and let it redeploy.
4. **Check.** `GET <api>/api/ready` returns 200, and a trip planned on the web app draws routes and the forecast.

The free API service sleeps after a quiet period; the app pings `/api/health` on load and says so while the server wakes up (about a minute).

## Assumptions and known limits

_To be filled in._

## Data sources and attribution

_To be filled in._

## License

[MIT](LICENSE)
