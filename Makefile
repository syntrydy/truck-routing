.PHONY: gen-api api-check be-lint be-type be-test be-sec fe-lint fe-type fe-test fe-build check

BACKEND := backend
FRONTEND := frontend
ARGS ?=

gen-api: ## regenerate the OpenAPI schema file and the frontend types from it
	cd $(BACKEND) && uv run python manage.py spectacular --format openapi-json --file openapi/schema.json
	cd $(FRONTEND) && npm run gen:api

api-check: gen-api ## fail when the checked-in schema or types are stale
	git diff --exit-code -- $(BACKEND)/openapi/schema.json $(FRONTEND)/src/api/schema.d.ts

be-lint: ## ruff lint and format check
	cd $(BACKEND) && uv run ruff check . && uv run ruff format --check .

be-type: ## mypy (strict on planner.domain and planner.providers)
	cd $(BACKEND) && uv run mypy .

be-test: ## pytest with coverage; pass ARGS="-k name" to focus
	cd $(BACKEND) && uv run pytest $(ARGS)

be-sec: ## bandit static analysis and pip-audit dependency scan
	cd $(BACKEND) && uv run bandit -q -r config planner -c pyproject.toml
	cd $(BACKEND) && uv run pip-audit

fe-lint: ## eslint and prettier check
	cd $(FRONTEND) && npm run lint && npm run format:check

fe-type: ## tsc strict typecheck
	cd $(FRONTEND) && npm run typecheck

fe-test: ## vitest
	cd $(FRONTEND) && npm run test -- $(ARGS)

fe-build: ## production build
	cd $(FRONTEND) && npm run build

check: be-lint be-type be-test be-sec fe-lint fe-type fe-test fe-build ## everything CI runs
