.PHONY: be-lint be-type be-test be-sec check

BACKEND := backend
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

check: be-lint be-type be-test be-sec ## everything CI runs
