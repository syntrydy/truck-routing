.PHONY: be-lint be-type be-test be-sec fe-lint fe-type fe-test fe-build check

BACKEND := backend
FRONTEND := frontend
ARGS ?=

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
