# Wenrix Channel Relay v2 - task runner
# Package manager is uv (never pip). Run `just` to list all recipes.

# Coverage threshold mirrors ci.yml.
cov_threshold := "85"

# List available recipes.
default:
    @just --list

# One-command local CI mirroring .github/workflows/ci.yml (fail fast, no retries).
ci: sync precommit cov

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
    uv run pytest -n auto --timeout=60

# Run tests excluding end-to-end tests.
test-fast:
    uv run pytest -n auto --timeout=60 -m "not e2e"

# Run tests with coverage and enforce the coverage gate.
cov:
    uv run pytest -n auto --timeout=60 --cov=src --cov-report=term-missing --cov-fail-under={{cov_threshold}}

# Run the relay locally with autoreload.
run:
    uv run uvicorn channel_relay.main:app --reload

# Start the local stack via docker compose.
up:
    docker compose up

# Build the production image (multi-stage, non-root, alpine runtime).
docker-build tag="wenrix-proxy:latest":
    docker build --target runtime -t {{tag}} .

# Lint + render the Helm chart and run its assertion tests (requires helm).
helm-test:
    helm lint deployment/helm/chart --set networkPolicy.ingressFromCIDRs='{10.0.0.0/8}'
    uv run pytest tests/deployment/test_helm_chart.py --no-cov

# Run the k6 load/perf harness against a locally-started relay + mock (requires k6).
perf payload_size="2048":
    #!/usr/bin/env bash
    set -euo pipefail
    MOCK_PORT=9000 MOCK_LATENCY_MS=50 uv run python deployment/mock_channel.py &
    mock_pid=$!
    RELAY_CONFIG_FILE=perf/relay.perf.json RELAY_BASIC_AUTH_ENABLED=false \
      RELAY_PII_KEYRING="{\"0\":\"$(head -c32 /dev/urandom | base64)\"}" RELAY_PII_KEY_EPOCH_ACTIVE=0 \
      uv run uvicorn channel_relay.main:app --port 8080 &
    relay_pid=$!
    trap 'kill $mock_pid $relay_pid 2>/dev/null || true' EXIT
    for _ in $(seq 1 30); do curl -fsS http://127.0.0.1:8080/readiness && break; sleep 1; done
    k6 run -e RELAY_URL=http://127.0.0.1:8080 -e PAYLOAD_SIZE={{payload_size}} perf/relay-load.js

# Run all pre-commit hooks against the whole tree.
precommit:
    uv run pre-commit run --all-files
