# Variables
REPONAME = demo-pydantic-schemaforms
APP_VERSION = 26.3.8.3
PYTHON ?= python3.14
PIP = $(PYTHON) -m pip
PYTEST = $(PYTHON) -m pytest

# Some devcontainers install CLI tools into ~/.local/bin which may not be on PATH.
BUMPCALVER = $(if $(wildcard $(HOME)/.local/bin/bumpcalver),$(HOME)/.local/bin/bumpcalver,bumpcalver)

EXAMPLE_PATH = examples
SERVICE_PATH = src

TESTS_PATH = tests
SQLITE_PATH = _sqlite_db
LOG_PATH = log

PORT = 5000
WORKER = 8
LOG_LEVEL = debug

DOCKER ?= docker
DOCKER_GROUP ?= dockerhost

REQUIREMENTS_PATH = requirements.txt

# Container publishing
# Override these at call time, e.g.:
#   make docker-push DOCKER_REPO=myuser/$(REPONAME)
DOCKER_REGISTRY ?= docker.io
DOCKER_REPO ?= mikeryan56/$(REPONAME)

.PHONY: alembic-revision alembic-upgrade ensure-alembic bump bump-undo bump-undo-id bump-history autoflake black cleanup create-docs flake8 help install isort run-example run-example-dev speedtest test smoke-live

ALEMBIC_REV_ID = $(subst .,_,$(APP_VERSION))


check-python: ## Verify Python >= 3.14 is available
	@$(PYTHON) -c "import sys; assert sys.version_info >= (3,14), f'Python >= 3.14 required (found {sys.version.split()[0]})'" 2>/dev/null \
		|| (echo "ERROR: Python >= 3.14 is required. In the devcontainer, rebuild so python3.14 is available, then run: make install"; exit 2)


autoflake: ## Remove unused imports and unused variables from Python code
	autoflake --in-place --remove-all-unused-imports  --ignore-init-module-imports --remove-unused-variables -r $(SERVICE_PATH)
	autoflake --in-place --remove-all-unused-imports  --ignore-init-module-imports --remove-unused-variables -r $(TESTS_PATH)
	autoflake --in-place --remove-all-unused-imports  --ignore-init-module-imports --remove-unused-variables -r $(EXAMPLE_PATH)

black: ## Reformat Python code to follow the Black code style
	$(PYTHON) -m black $(SERVICE_PATH)
	# black $(TESTS_PATH)
	# black $(EXAMPLE_PATH)


bump: ## Bump the version of the project and create an Alembic revision
	@set -e; \
	old_ver="$(APP_VERSION)"; \
	$(BUMPCALVER) --build; \
	new_ver=$$(awk -F= '/^APP_VERSION[[:space:]]*=/ {gsub(/[[:space:]]/,"",$$2); print $$2; exit}' makefile); \
	if [ -z "$$new_ver" ]; then echo "ERROR: could not read APP_VERSION from makefile after bump"; exit 2; fi; \
	if [ "$$old_ver" = "$$new_ver" ]; then \
		echo "(skipped) APP_VERSION unchanged ($$new_ver); not creating Alembic revision"; \
	else \
		$(MAKE) --no-print-directory alembic-revision; \
	fi


bump-undo: ## Undo the last bumpcalver operation (rollback version changes)
	@$(BUMPCALVER) --undo


bump-undo-id: ## Undo a specific bumpcalver operation (set UNDO_ID=...)
	@if [ -z "$(UNDO_ID)" ]; then echo "ERROR: UNDO_ID is required. Example: make bump-undo-id UNDO_ID=20260308_004052_844"; exit 2; fi
	@$(BUMPCALVER) --undo-id "$(UNDO_ID)"


bump-history: ## List recent bumpcalver operations that can be undone
	@$(BUMPCALVER) --list-history


cleanup: isort ruff autoflake ## Run isort, ruff, autoflake


flake8: ## Run flake8 to check Python code for PEP8 compliance
	flake8 --tee . > htmlcov/_flake8Report.txt

help:  ## Display this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)


install: check-python ## Install the project's dependencie
	$(PIP) install -r $(REQUIREMENTS_PATH)



reinstall: check-python ## Install the project's dependencie
	$(PIP) uninstall -r $(REQUIREMENTS_PATH) -y
	$(PIP) install -r $(REQUIREMENTS_PATH)

isort: ## Sort imports in Python code
	$(PYTHON) -m isort $(SERVICE_PATH)
	$(PYTHON) -m isort $(TESTS_PATH)
	$(PYTHON) -m isort $(EXAMPLE_PATH)

test: ## Run the project's tests (linting + pytest + coverage badges)
	@start=$$(date +%s); \
	echo "🔍 Running pre-commit (ruff, formatting, yaml/toml checks)..."; \
	$(PYTHON) -m pre_commit run -a; \
	echo "✅ Pre-commit passed. Running pytest..."; \
	$(PYTHON) -m pytest -n 2; \
	echo "📊 Generating coverage and test badges..."; \
	genbadge coverage -i /workspaces/$(REPONAME)/coverage.xml 2>/dev/null || true; \
	genbadge tests -i /workspaces/$(REPONAME)/report.xml 2>/dev/null || true; \
	sed -i "s|<source>/workspaces/$(REPONAME)</source>|<source>$$(pwd)</source>|" coverage.xml; \
	end=$$(date +%s); \
	$(PYTHON) -c "print(f'✨ Tests complete. Badges updated. Total time: {$$end - $$start:.2f} seconds')"

tests: test ## Alias for 'test' - Run the project's tests


smoke-live: ## Run live-server smoke test against a running app on localhost
	$(PYTHON) scripts/smoke_live_server.py --base-url http://localhost:$(PORT)


ruff: ## Format Python code with Ruff
	$(PYTHON) -m ruff check --fix --exit-non-zero-on-fix --show-fixes $(SERVICE_PATH)
	$(PYTHON) -m ruff check --fix --exit-non-zero-on-fix --show-fixes $(TESTS_PATH)
	$(PYTHON) -m ruff check --fix --exit-non-zero-on-fix --show-fixes $(EXAMPLE_PATH)



run: check-python ## Run the demo FastAPI app (async implementation)
	$(PYTHON) -m uvicorn src.main:app --host 127.0.0.1 --port $(PORT) --reload --log-level $(LOG_LEVEL)



ex-run: check-python ## Run the FastAPI example (async implementation)
	cd examples && $(PYTHON) -m uvicorn fastapi_example:app --port 5000 --reload --log-level $(LOG_LEVEL)


kill:  # Kill any process running on the app port
	@echo "Stopping any process running on port ${PORT}..."
	@lsof -ti:${PORT} | xargs -r kill -9 || echo "No process found running on port ${PORT}"
	@echo "Port ${PORT} is now free"

docker-build: ## Build the Docker image for the demo app
	@echo "🔁 Alembic smoke-test (best-effort) (APP_VERSION=$(APP_VERSION))..."
	@$(PYTHON) -c "import alembic" >/dev/null 2>&1 \
		&& (ANALYTICS_DB_PATH=/tmp/schemaforms_alembic_smoke.sqlite $(PYTHON) -m alembic -c alembic.ini upgrade head && rm -f /tmp/schemaforms_alembic_smoke.sqlite) \
		|| echo "(skipped) alembic not installed in host Python; Docker build will smoke-test migrations inside the image"
	@set -e; cmd='$(DOCKER) build --no-cache -t $(REPONAME):$(APP_VERSION) .'; \
		$(DOCKER) info >/dev/null 2>&1 && eval "$$cmd" \
		|| (newgrp $(DOCKER_GROUP) -c "$(DOCKER) info" >/dev/null 2>&1 && newgrp $(DOCKER_GROUP) -c "$$cmd") \
		|| (echo "ERROR: Docker daemon not accessible (permission denied). Try: newgrp $(DOCKER_GROUP) -c 'make docker-deploy'"; exit 2)

docker-push: ## Push the Docker image to Docker Hub
	@set -e; tag_cmd='$(DOCKER) tag $(REPONAME):$(APP_VERSION) $(DOCKER_REGISTRY)/$(DOCKER_REPO):$(APP_VERSION)'; push_cmd='$(DOCKER) push $(DOCKER_REGISTRY)/$(DOCKER_REPO):$(APP_VERSION)'; \
		$(DOCKER) info >/dev/null 2>&1 && (eval "$$tag_cmd" && eval "$$push_cmd") \
		|| (newgrp $(DOCKER_GROUP) -c "$(DOCKER) info" >/dev/null 2>&1 && newgrp $(DOCKER_GROUP) -c "$$tag_cmd" && newgrp $(DOCKER_GROUP) -c "$$push_cmd") \
		|| (echo "ERROR: Docker daemon not accessible (permission denied). Try: newgrp $(DOCKER_GROUP) -c 'make docker-push'"; exit 2)

docker-run: ## Run the Docker container for the demo app
	@set -e; cmd='$(DOCKER) run -d -p $(PORT):$(PORT) -v $(SQLITE_PATH):/data -e ANALYTICS_DB_PATH=/data/schemaforms_analytics.sqlite -e IP_GEO_ENABLED=1 -e IP_GEO_WORKER_ENABLED=1 -e IP_GEO_RATE_LIMIT_PER_MIN=40 --name $(REPONAME)_container $(REPONAME):$(APP_VERSION)'; \
		$(DOCKER) info >/dev/null 2>&1 && eval "$$cmd" \
		|| (newgrp $(DOCKER_GROUP) -c "$(DOCKER) info" >/dev/null 2>&1 && newgrp $(DOCKER_GROUP) -c "$$cmd") \
		|| (echo "ERROR: Docker daemon not accessible (permission denied). Try: newgrp $(DOCKER_GROUP) -c 'make docker-run'"; exit 2)

ensure-alembic: check-python ## Ensure Alembic is installed in the active Python
	@$(PYTHON) -c "import alembic" >/dev/null 2>&1 || (echo "Installing Python dependencies (required for Alembic)..."; $(PIP) install -r $(REQUIREMENTS_PATH))


alembic-upgrade: ensure-alembic ## Run Alembic migrations against ANALYTICS_DB_PATH
	$(PYTHON) -m alembic -c alembic.ini upgrade head

alembic-revision: ensure-alembic ## Create an Alembic revision named by APP_VERSION
	@set -e; \
	existing=$$(ls -1 migrations/versions/$(ALEMBIC_REV_ID)_*.py 2>/dev/null | head -n 1 || true); \
	if [ -n "$$existing" ]; then \
		echo "(skipped) Alembic revision already exists for APP_VERSION=$(APP_VERSION): $$existing"; \
	else \
		$(PYTHON) -m alembic -c alembic.ini revision -m "$(APP_VERSION)" --rev-id "$(ALEMBIC_REV_ID)"; \
	fi

docker-deploy: docker-build docker-push ## Build, push, and run the Docker container for the demo app
