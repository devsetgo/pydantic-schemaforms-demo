# Variables
REPONAME = demo-pydantic-schemaforms
APP_VERSION = 26.3.6.1
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

REQUIREMENTS_PATH = requirements.txt

# Container publishing
# Override these at call time, e.g.:
#   make docker-push DOCKER_REPO=myuser/$(REPONAME)
DOCKER_REGISTRY ?= docker.io
DOCKER_REPO ?= mikeryan56/$(REPONAME)

.PHONY: alembic-revision alembic-upgrade autoflake black cleanup create-docs flake8 help install isort run-example run-example-dev speedtest test smoke-live

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

bump: ## Bump the version of the project
	$(BUMPCALVER) --build


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
	docker build --no-cache -t $(REPONAME):${APP_VERSION} .

docker-push: ## Push the Docker image to Docker Hub
	docker tag $(REPONAME):${APP_VERSION} $(DOCKER_REGISTRY)/$(DOCKER_REPO):${APP_VERSION}
	docker push $(DOCKER_REGISTRY)/$(DOCKER_REPO):${APP_VERSION}

docker-run: ## Run the Docker container for the demo app
	docker run -d \
		-p $(PORT):$(PORT) \
		-v $(SQLITE_PATH):/data \
		-e ANALYTICS_DB_PATH=/data/schemaforms_analytics.sqlite \
		-e IP_GEO_ENABLED=1 \
		-e IP_GEO_WORKER_ENABLED=1 \
		-e IP_GEO_RATE_LIMIT_PER_MIN=40 \
		--name $(REPONAME)_container \
		$(REPONAME):${APP_VERSION}

alembic-upgrade: ## Run Alembic migrations against ANALYTICS_DB_PATH
	$(PYTHON) -m alembic -c alembic.ini upgrade head

alembic-revision: ## Create an Alembic revision named by APP_VERSION
	$(PYTHON) -m alembic -c alembic.ini revision -m "$(APP_VERSION)" --rev-id "$(ALEMBIC_REV_ID)"

docker-deploy: docker-build docker-push ## Build, push, and run the Docker container for the demo app