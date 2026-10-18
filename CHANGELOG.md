# Changelog

All notable changes, generated from the Conventional Commit history.

## [1.0.0] - 2026-10-18

First release.

### Features

- **domain:** value objects and risk levels ([#16](https://github.com/syntrydy/truck-routing/pull/16))
- **domain:** weather band classification ([#18](https://github.com/syntrydy/truck-routing/pull/18))
- **domain:** load rules, checkpoint level and reasons ([#20](https://github.com/syntrydy/truck-routing/pull/20))
- **domain:** geometry utilities ([#22](https://github.com/syntrydy/truck-routing/pull/22))
- **domain:** checkpoint sampling with truck ETAs ([#24](https://github.com/syntrydy/truck-routing/pull/24))
- **domain:** select weather at ETA ([#26](https://github.com/syntrydy/truck-routing/pull/26))
- **domain:** route scoring ([#28](https://github.com/syntrydy/truck-routing/pull/28))
- **domain:** ranking and recommendation reason ([#30](https://github.com/syntrydy/truck-routing/pull/30))
- **domain:** route candidate selection ([#32](https://github.com/syntrydy/truck-routing/pull/32))
- **domain:** corridor heatmap grid ([#34](https://github.com/syntrydy/truck-routing/pull/34))
- **infra:** resilient HTTP client ([#36](https://github.com/syntrydy/truck-routing/pull/36))
- **infra:** cache layer with stale-if-error ([#38](https://github.com/syntrydy/truck-routing/pull/38))
- **providers:** OSRM routing adapter ([#40](https://github.com/syntrydy/truck-routing/pull/40))
- **providers:** openrouteservice fallback and routing chain ([#49](https://github.com/syntrydy/truck-routing/pull/49))
- **providers:** Open-Meteo weather adapter ([#51](https://github.com/syntrydy/truck-routing/pull/51))
- **providers:** geocoding adapters ([#53](https://github.com/syntrydy/truck-routing/pull/53))
- **service:** plan orchestration facade ([#57](https://github.com/syntrydy/truck-routing/pull/57))
- **api:** POST /api/plan with validation and error mapping ([#59](https://github.com/syntrydy/truck-routing/pull/59))
- **api:** geocode endpoint, readiness and rate limiting ([#61](https://github.com/syntrydy/truck-routing/pull/61))
- **api:** production hardening and observability ([#63](https://github.com/syntrydy/truck-routing/pull/63))
- **web:** typed API client ([#65](https://github.com/syntrydy/truck-routing/pull/65))
- **web:** app shell and map ([#67](https://github.com/syntrydy/truck-routing/pull/67))
- **web:** trip form with place autocomplete ([#69](https://github.com/syntrydy/truck-routing/pull/69))
- **web:** routes and checkpoints on the map ([#71](https://github.com/syntrydy/truck-routing/pull/71))
- **web:** route cards and banners ([#73](https://github.com/syntrydy/truck-routing/pull/73))
- **web:** corridor heatmap with forecast slider ([#75](https://github.com/syntrydy/truck-routing/pull/75))
- **web:** loading, cold-start, error and mobile states ([#77](https://github.com/syntrydy/truck-routing/pull/77))
- **providers:** add a National Weather Service weather fallback ([#95](https://github.com/syntrydy/truck-routing/pull/95))
- **web:** start the trip form with a default origin and destination ([#97](https://github.com/syntrydy/truck-routing/pull/97))

### Fixes

- **deploy:** use the host Render assigned to the API ([#85](https://github.com/syntrydy/truck-routing/pull/85))
- **deps:** declare httpx as a runtime dependency ([#89](https://github.com/syntrydy/truck-routing/pull/89))
- **providers:** log lost weather batches and honour Retry-After ([#91](https://github.com/syntrydy/truck-routing/pull/91))

### Performance

- **web:** performance pass ([#79](https://github.com/syntrydy/truck-routing/pull/79))

### Documentation

- write the README and the decision records ([#87](https://github.com/syntrydy/truck-routing/pull/87))
- **deploy:** add live links and deployment notes ([#93](https://github.com/syntrydy/truck-routing/pull/93))
- **backlog:** mark B-36 done ([#98](https://github.com/syntrydy/truck-routing/pull/98))

### Tests

- pin the sampling, grid, overlap and rain-precision boundaries ([#55](https://github.com/syntrydy/truck-routing/pull/55))
- **e2e:** add a browser smoke test against recorded data ([#81](https://github.com/syntrydy/truck-routing/pull/81))

### Continuous integration

- GitHub Actions, CodeQL and Dependabot ([#10](https://github.com/syntrydy/truck-routing/pull/10))

### Chores

- initial commit with specification and backlog
- scaffold monorepo layout ([#2](https://github.com/syntrydy/truck-routing/pull/2))
- **backend:** Django + DRF project with env settings and health endpoint ([#4](https://github.com/syntrydy/truck-routing/pull/4))
- **backend:** lint, type, test and security tooling ([#6](https://github.com/syntrydy/truck-routing/pull/6))
- **frontend:** Vite React TS scaffold with strict linting ([#8](https://github.com/syntrydy/truck-routing/pull/8))
- pre-commit hooks ([#14](https://github.com/syntrydy/truck-routing/pull/14))
- **deps:** upgrade Django to 6.1 ([#43](https://github.com/syntrydy/truck-routing/pull/43))
- **deps:** upgrade the frontend dependency group (React 19) ([#44](https://github.com/syntrydy/truck-routing/pull/44))
- **deps:** keep jsdom on 29 until the minimum Node version is raised ([#47](https://github.com/syntrydy/truck-routing/pull/47))
- **deploy:** add Render and Vercel configuration ([#83](https://github.com/syntrydy/truck-routing/pull/83))
- final quality audit ([#100](https://github.com/syntrydy/truck-routing/pull/100))

[1.0.0]: https://github.com/syntrydy/truck-routing/releases/tag/v1.0.0
