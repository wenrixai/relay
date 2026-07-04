# deployment-ci Specification

## Purpose
TBD - created by archiving change slice-1-mvp. Update Purpose after archive.
## Requirements
### Requirement: Alpine container image
The relay SHALL ship a multi-stage Alpine image that runs as a non-root user, installs musllinux
wheels for lxml/cryptography (no compiler in the final stage), and defines a healthcheck against
`/readiness`.

#### Scenario: Container healthcheck
- **WHEN** the container starts and the app is ready
- **THEN** the healthcheck against `/readiness` succeeds

### Requirement: CI pipeline
CI SHALL run, on every push/PR, `uv sync --frozen` → ruff lint → `ruff format --check` → mypy strict
→ pylint → pytest (timeout + coverage gate) → image build → `/readiness` smoke, failing fast with no
retries.

#### Scenario: CI enforces the full gate
- **WHEN** a change is pushed
- **THEN** CI runs the full lint/type/test/build/smoke pipeline and fails on any step

### Requirement: Security automation
The repository SHALL configure Dependabot, CodeQL, gitleaks, dependency audit, and Trivy image
scanning, plus CODEOWNERS and a PR template.

#### Scenario: Security workflows present
- **WHEN** the repository is scanned
- **THEN** Dependabot, CodeQL, gitleaks, dependency audit, and Trivy jobs are configured
