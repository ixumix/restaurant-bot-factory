.PHONY: help install run lint typecheck test check format

PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*##"; printf "\nTargets:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

install: ## Create venv and install dev dependencies
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e ".[dev]"

run: ## Run the constructor bot (long polling)
	$(BIN)/python -m bot_factory

lint: ## Run ruff
	$(BIN)/ruff check .

format: ## Apply ruff auto-fixes (incl. import sorting)
	$(BIN)/ruff check --fix .

typecheck: ## Run mypy on src/
	$(BIN)/mypy src

test: ## Run pytest
	$(BIN)/pytest -q

check: lint typecheck test ## Run lint + typecheck + tests
