# Wenrix Channel Relay v2 - task runner
# Package manager is uv (never pip). Run `just` to list all recipes.

# Coverage threshold mirrors ci.yml.
cov_threshold := "85"

# List available recipes.
default:
    @just --list

# One-command local CI mirroring .github/workflows/ci.yml (fail fast, no retries).
ci: sync lint fmt-check types pylint test

# Sync the locked environment.
sync:
    uv sync --frozen

# Lint with ruff.
lint:
    uv run ruff check .

# Format with ruff (writes changes).
fmt:
    uv run ruff format .

# Check formatting without writing (used in CI).
fmt-check:
    uv run ruff format --check .

# Static type check with mypy (strict configured in pyproject).
types:
    uv run mypy src

# Lint with pylint.
pylint:
    uv run pylint src

# Run the test suite (pytest-timeout enforces no slow tests).
test:
    uv run pytest --timeout=60

# Run tests excluding end-to-end tests.
test-fast:
    uv run pytest --timeout=60 -m "not e2e"

# Run tests with coverage and enforce the coverage gate.
cov:
    uv run pytest --timeout=60 --cov=src --cov-report=term-missing --cov-fail-under={{cov_threshold}}

# Run the relay locally with autoreload.
run:
    uv run uvicorn channel_relay.main:app --reload

# Start the local stack via docker compose.
up:
    docker compose up

# Run all pre-commit hooks against the whole tree.
precommit:
    uv run pre-commit run --all-files
