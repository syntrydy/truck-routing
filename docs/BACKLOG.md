# Backlog

Ordered work items. Work strictly top to bottom unless an item is blocked. Each item becomes exactly one GitHub issue and one PR. When an issue is created, write its number after the title (`— #12`); tick the box in the same PR that closes it.

Conventions: titles follow Conventional Commits; labels are `type:*` and `area:*`; milestones `M0`–`M5`. Acceptance criteria (AC) are the contract — a PR is mergeable only when every AC holds and the Definition of Done in `docs/SPEC.md` §11 is met.

---

## M0 — Foundations

- [x] **B-01 chore: scaffold monorepo layout — #1** — `type:chore` `area:infra`
  - Create `backend/`, `frontend/`, `docs/`, `.github/`; MIT `LICENSE`; `.editorconfig`; `.gitignore` (Python, Node, env files, OS junk); `README.md` skeleton (title, one-line pitch, sections to fill later).
  - AC: tree matches SPEC §10 top level; `.env*` ignored except `.env.example`.

- [x] **B-02 chore(backend): Django + DRF project with env settings and health endpoint — #3** — `type:chore` `area:backend`
  - uv project (Python 3.12), Django 5, DRF, drf-spectacular, django-environ, django-cors-headers; `config/settings.py` fully env-driven; app `planner`; `GET /api/health` → `{"status":"ok"}`; `/api/schema/`.
  - AC: `uv run python manage.py check` passes; `.env.example` documents every variable; health test passes.

- [x] **B-03 chore(backend): lint, type, test and security tooling — #5** — `type:chore` `area:backend`
  - ruff (rules: E, F, W, I, B, UP, S, SIM, RET, PL, PT, N, C4, DTZ, ERA), ruff format, mypy (strict for `planner.domain` and `planner.providers`), pytest + pytest-django + pytest-cov + respx + hypothesis, bandit, pip-audit. Root `Makefile` targets: `be-lint`, `be-type`, `be-test`, `be-sec`, `check`.
  - AC: `make check` green on the empty project; coverage report generated.

- [x] **B-04 chore(frontend): Vite React TS scaffold with strict linting — #7** — `type:chore` `area:frontend`
  - Vite + React 18 + TS strict (`noUncheckedIndexedAccess`), eslint flat config (typescript-eslint strict-type-checked, react-hooks, jsx-a11y), prettier, vitest + Testing Library. Makefile targets `fe-lint`, `fe-type`, `fe-test`, `fe-build` wired into `check`.
  - AC: `make check` green; sample component test passes.

- [x] **B-05 ci: GitHub Actions, CodeQL and Dependabot — #9** — `type:chore` `area:infra`
  - Workflow on PR + push to main: backend job (uv sync --frozen, ruff check, ruff format --check, mypy, pytest with coverage gate, bandit, pip-audit, `manage.py check --deploy` with prod-like env); frontend job (npm ci, typecheck, eslint, vitest, build, `npm audit --audit-level=high`); gitleaks job. CodeQL workflow (python, javascript-typescript). `dependabot.yml` weekly for pip/uv, npm, github-actions. Concurrency group cancels superseded runs. Actions pinned to major versions.
  - AC: CI green on this PR; failing lint demonstrably fails the job (verified then reverted locally).

- [x] **B-06 chore: pre-commit hooks — #11** — `type:chore` `area:infra`
  - `.pre-commit-config.yaml`: ruff, ruff-format, mypy (domain/providers), prettier, eslint (frontend changes), gitleaks, check-yaml, check-json, end-of-file-fixer, trailing-whitespace, detect-private-key, check-added-large-files. README "Development" section explains `pre-commit install`.
  - AC: `pre-commit run --all-files` passes.

## M1 — Domain (pure, no I/O)

- [x] **B-07 feat(domain): value objects and risk levels — #15** — `type:feat` `area:backend`
  - `domain/models.py`: frozen dataclasses `LatLon`, `WeatherSample`, `Checkpoint`, `Stretch`, `RouteScore`; `RiskLevel` IntEnum + `UNKNOWN` sentinel handling helpers (`max_known`, `is_known`).
  - AC: mypy strict clean; unit tests for ordering and UNKNOWN semantics.

- [x] **B-08 feat(domain): weather band classification — #17** — `type:feat` `area:backend`
  - `domain/risk.py`: band tables as data; `classify_wind`, `classify_rain`, `classify_snow` per SPEC §4.5 boundaries; `None` → UNKNOWN.
  - AC: parameterized tests at every edge (e.g. 24.99/25, 34.99/35, 0.0999/0.10, 1.00/1.0001, 2.99/3.0/3.0001); hypothesis test that classification is monotonic non-decreasing.

- [x] **B-09 feat(domain): load rules, checkpoint level and reasons — #19** — `type:feat` `area:backend`
  - `assess(sample, load_lb, wind_basis) -> Assessment(level, factor_levels, reasons)`; load rules in order; UNKNOWN policy per SPEC §4.5; reason strings formatted consistently.
  - AC: tests for 47 mph × {30,000, 30,001} lb, 40 mph × {40,000, 40,001} lb, 55 mph × 0 lb, UNKNOWN rain with SEVERE wind stays SEVERE, UNKNOWN rain with LOW wind becomes UNKNOWN; gust basis switch.

- [x] **B-10 feat(domain): geometry utilities — #21** — `type:feat` `area:backend`
  - `domain/geometry.py`: haversine, cumulative distances, point-at-distance interpolation, bearing, perpendicular offset, Douglas-Peucker simplification (tolerance in meters), point-to-polyline distance.
  - AC: tests against known distances (±0.5%); simplification keeps endpoints; property test: interpolated point distance monotonic.

- [x] **B-11 feat(domain): checkpoint sampling with truck ETAs — #23** — `type:feat` `area:backend`
  - `domain/sampling.py`: apply truck speed cap per segment; sample at interval incl. destination; ETA interpolation; stretch lengths.
  - AC: trip shorter than interval → 2 checkpoints; destination always last; ETAs strictly increasing; speed cap test (fast segment slowed, slow segment untouched).

- [x] **B-12 feat(domain): select weather at ETA — #25** — `type:feat` `area:backend`
  - `domain/weather_select.py`: preceding-hour rule for precipitation, linear wind interpolation, `rain + showers`, out-of-range/null → None.
  - AC: tests for ETA exactly on the hour, 14:20 picks 15:00 precipitation, beyond series → None, nulls.

- [x] **B-13 feat(domain): route scoring — #27** — `type:feat` `area:backend`
  - `domain/scoring.py`: stretch level = worse endpoint; miles by level; unknown miles; distance-weighted avg risk; worst level; low-confidence flag.
  - AC: hand-computed fixtures; unknown miles excluded from average and never counted as LOW.

- [x] **B-14 feat(domain): ranking and recommendation reason — #29** — `type:feat` `area:backend`
  - `domain/ranking.py`: sort key per SPEC §4.7; reason from first separating criterion; NO_SAFE_ROUTE when all routes have No Travel miles.
  - AC: one test per tie-breaker level; No Travel outranks Severe; float-noise tie falls through; all-No-Travel → `None` + banner.

- [x] **B-15 feat(domain): route candidate selection — #31** — `type:feat` `area:backend`
  - `domain/routes_select.py`: via-point computation (both sides), overlap-based dedupe, detour-length rejection, top-3 by duration, notes.
  - AC: identical routes deduped; > 40% longer detour rejected; returns ≤ 3; note when < 3.

- [x] **B-16 feat(domain): corridor heatmap grid — #33** — `type:feat` `area:backend`
  - `domain/corridor.py`: buffered bbox, adaptive spacing to ≤ 200 points, corridor mask (25 km), frame assembly given point series.
  - AC: short and cross-country fixtures both ≤ 200 points and ≥ 20 points; all points within 25 km of a route.

## M2 — Infrastructure and providers

- [ ] **B-17 feat(infra): resilient HTTP client** — `type:feat` `area:backend`
  - `infra/http.py`: shared httpx client, per-provider timeouts, retry with full-jitter backoff (5xx/429/connect only), circuit breaker (3 failures, 60 s), deadline budget context, bulkhead semaphores, host allowlist, User-Agent from settings, typed exceptions (`UpstreamTimeout`, `UpstreamUnavailable`, `UpstreamError`, `UpstreamContractError`).
  - AC: respx tests for timeout, retry-then-success, no retry on 400, breaker opens and half-opens (time injected, no sleeps), deadline exhaustion, non-allowlisted host rejected.

- [ ] **B-18 feat(infra): cache layer with stale-if-error** — `type:feat` `area:backend`
  - `infra/cache.py`: cache-aside helper storing value + fetched_at; fresh TTL and stale window; key builders with coordinate rounding; LocMem default, Redis via `REDIS_URL`.
  - AC: tests for hit, miss, stale served on loader error with flag, stale window expiry raises.

- [ ] **B-19 feat(providers): OSRM routing adapter** — `type:feat` `area:backend`
  - Protocol `RoutingProvider`; OSRM adapter (route with alternatives, route via waypoint), 1.1 s spacing lock, maps response to domain types incl. per-segment annotations and snap distance, NoRoute mapping.
  - AC: recorded fixtures for 3-route, 1-route, NoRoute, malformed JSON; lock spacing verified with injected clock.

- [ ] **B-20 feat(providers): openrouteservice fallback and routing chain** — `type:feat` `area:backend`
  - ORS `driving-hgv` adapter (only when `ORS_API_KEY` set); `FallbackRoutingProvider` chain; `meta.routing_source` reflects provider used.
  - AC: chain falls through on `UpstreamUnavailable`; skipped when no key; fixtures only.

- [ ] **B-21 feat(providers): Open-Meteo weather adapter** — `type:feat` `area:backend`
  - Batching ≤ 100 points, ≤ 4 concurrent, unit assertion, per-point caching via B-18, returns hourly series keyed by rounded point.
  - AC: unit mismatch raises contract error; batching splits 250 points into 3 calls; cache prevents second call; stale served on outage.

- [ ] **B-22 feat(providers): geocoding adapters** — `type:feat` `area:backend`
  - Photon adapter + Nominatim fallback (1 req/s lock), normalized `Place(label, lat, lon, kind)`, 24 h cache.
  - AC: fixtures; fallback on Photon failure; label includes region and country.

## M3 — Application and API

- [ ] **B-23 feat(service): plan orchestration facade** — `type:feat` `area:backend`
  - `services/plan.py` wiring providers + domain end to end; `services/container.py` DI from settings; deadline budget per request; partial weather failure path; notes and banners.
  - AC: service test on fixtures returns full result; weather outage → UNKNOWN + `WEATHER_UNAVAILABLE`; routing outage → typed error.

- [ ] **B-24 feat(api): POST /api/plan with validation and error mapping** — `type:feat` `area:backend`
  - DRF serializers per SPEC §5, error envelope, status mapping, drf-spectacular annotations, response compaction (geometry simplified, floats rounded).
  - AC: API tests for each validation rule and each error code; schema contains request/response components; payload for fixture trip ≤ 300 KB gzipped.

- [ ] **B-25 feat(api): geocode endpoint, readiness and rate limiting** — `type:feat` `area:backend`
  - `GET /api/geocode`, `GET /api/ready`, django-ratelimit on plan and geocode with JSON 429.
  - AC: tests for min/max query length, 429 envelope, ready reports breaker states.

- [ ] **B-26 feat(api): production hardening and observability** — `type:feat` `area:backend`
  - Request-ID middleware, JSON logging with per-plan metrics, GZip middleware, security settings per SPEC §8, gunicorn config.
  - AC: `check --deploy` clean with prod env; logs contain request_id and metrics; coordinates truncated in logs.

## M4 — Frontend

- [ ] **B-27 feat(web): typed API client** — `type:feat` `area:frontend`
  - Generate types with openapi-typescript (`npm run gen:api` from a checked-in schema file); fetch wrapper with timeout, error envelope parsing, request id surfaced; TanStack Query setup; `/api/health` warm-up on load.
  - AC: tests for error parsing and timeout; generated types committed and CI checks they are up to date.

- [ ] **B-28 feat(web): app shell and map** — `type:feat` `area:frontend`
  - Layout (panel + map + slider slot), MapLibre lazy-loaded, OpenFreeMap style, attribution control, `useMap` hook creating the map once.
  - AC: map renders; no re-creation on state change (test or dev assertion); attribution visible.

- [ ] **B-29 feat(web): trip form with place autocomplete** — `type:feat` `area:frontend`
  - `PlaceInput` (debounced 300 ms, keyboard navigable combobox, aria), datetime-local with timezone label, load input, interval segmented control, client validation mirroring the API, stale-inputs detection.
  - AC: component tests for debounce, keyboard selection, validation messages; axe check passes.

- [ ] **B-30 feat(web): routes and checkpoints on the map** — `type:feat` `area:frontend`
  - Route line layers (recommended emphasized), single checkpoint source with data-driven colors, popups with ETA/weather/reasons, fit bounds after plan, hover/select sync with cards.
  - AC: layer data built in pure functions with unit tests; popup content test.

- [ ] **B-31 feat(web): route cards and banners** — `type:feat` `area:frontend`
  - Rank badge, duration, distance, stacked miles-by-level bar with text labels, reason, low-confidence badge, banners (NO_SAFE_ROUTE, WEATHER_UNAVAILABLE, notes).
  - AC: tests for each banner; bar has accessible text equivalent.

- [ ] **B-32 feat(web): corridor heatmap with forecast slider** — `type:feat` `area:frontend`
  - Frames precomputed with `useMemo`, `setData` on slider change via rAF, play/pause, keyboard, variable toggle, unknown cells grey, zoom fade to circles, truck marker on selected route at slider hour.
  - AC: frame builder unit-tested; slider interaction test; manual perf check recorded in PR (fps from Performance panel).

- [ ] **B-33 feat(web): loading, cold-start, error and mobile states** — `type:feat` `area:frontend`
  - Cold-start message after 3 s without health response, progress steps, error messages per code with suggestions, mobile bottom sheet, focus management.
  - AC: tests for each state; Lighthouse accessibility ≥ 95 on the built app.

- [ ] **B-34 perf(web): performance pass** — `type:perf` `area:frontend`
  - Bundle analysis, code-split MapLibre, memo audit, avoid re-renders on slider (React profiler), verify budgets in SPEC §7.
  - AC: budgets met and numbers recorded in PR description.

## M5 — Delivery

- [ ] **B-35 test(e2e): Playwright smoke test** — `type:test` `area:frontend`
  - Backend in fixture mode (`PROVIDERS_MODE=fixtures` serving recorded responses); test plans a trip, sees 3 routes, opens a checkpoint popup, moves slider. Runs in CI.
  - AC: green in CI; fixture mode impossible to enable when `DEBUG=False` unless explicitly allowed.

- [ ] **B-36 chore(deploy): Render and Vercel configuration** — `type:chore` `area:infra`
  - `render.yaml`, `vercel.json` (SPA rewrite + security headers/CSP), env var docs, deploy steps in README.
  - AC: both deployed; `/api/ready` healthy; CORS limited to the Vercel origin; production smoke check passes.

- [ ] **B-37 docs: README and decision records** — `type:docs` `area:infra`
  - README: overview, live links, architecture diagram (mermaid), how it works (pipeline), assumptions register, API summary, local setup in ≤ 3 commands, testing, security scanning, known limits, scaling path. ADRs in `docs/adr/` for: routing provider choice, risk boundary interpretation, No Travel ranking, single-payload heatmap.
  - AC: a new developer can run the app locally from the README alone.

- [ ] **B-38 chore: final quality audit** — `type:chore` `area:infra`
  - All scanners clean (no ignored high findings without justification), coverage gates met, dependency versions current, no TODOs, PR/issue history tidy, release tag `v1.0.0` with changelog generated from Conventional Commits.
  - AC: checklist in the PR fully ticked.
