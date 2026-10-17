# Weather-Aware Truck Routing

A web app that recommends the safest truck route between two places, based on the weather along the route at the estimated arrival time, the load weight and the travel time.

## Features

_To be filled in._

## Architecture

_To be filled in. See [`docs/SPEC.md`](docs/SPEC.md) for the technical specification._

## Getting started

_To be filled in._

## Configuration

_To be filled in._

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

_To be filled in._

## Assumptions and known limits

_To be filled in._

## Data sources and attribution

_To be filled in._

## License

[MIT](LICENSE)
