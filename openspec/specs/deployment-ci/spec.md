# deployment-ci Specification

## Purpose
Define build, security, deployment, release, and performance automation for the relay.
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
scanning, plus CODEOWNERS and a PR template. Security jobs SHALL execute on organization pull
requests using standard repository credentials and SHALL fail on security findings rather than
missing optional commercial scanner credentials or invalid local-project dependency resolution.

#### Scenario: Security workflows present
- **WHEN** the repository is scanned
- **THEN** Dependabot, CodeQL, gitleaks, dependency audit, and Trivy jobs are configured

#### Scenario: Security jobs execute on dependency-update pull requests
- **WHEN** an organization dependency bot opens a pull request
- **THEN** CodeQL can check out and analyze the repository, gitleaks scans the checked-out history
  without an optional license secret, and dependency audit scans the locked third-party production
  dependencies without attempting to install the editable relay project

### Requirement: AWS ECS Fargate infrastructure-as-code
The repository SHALL provide two equivalent, self-contained IaC paths — Terraform under
`deployment/terraform/` and CloudFormation under `deployment/cloudformation/` — that deploy the relay
as a highly available ECS Fargate service. Each SHALL provision a multi-AZ VPC (public subnets for the
load balancer, private subnets with NAT egress for tasks), an ALB whose target group health check
targets `/readiness`, an ECS service with at least two tasks spread across availability zones and
autoscaling on CPU or request count, and CloudWatch logging. Task containers SHALL run non-root with a
read-only root filesystem.

#### Scenario: Terraform configuration is valid
- **WHEN** `terraform init && terraform validate` runs against `deployment/terraform/`
- **THEN** the configuration validates without error

#### Scenario: CloudFormation template is valid
- **WHEN** the CloudFormation template is linted
- **THEN** it passes `cfn-lint` and describes a multi-AZ ECS Fargate service

### Requirement: AWS deployment secret and network hardening
The AWS IaC SHALL source the PII master keyring from AWS Secrets Manager (encrypted at rest, never in
plaintext) and inject it into the task as `RELAY_PII_KEYRING`; the task execution role SHALL be scoped
to read only that secret. ALB ingress SHALL be restricted to a configurable Wenrix client CIDR, and the
task security group SHALL accept traffic only from the ALB security group. The secret SHALL carry a
retain-on-delete policy so stack deletion never orphans outstanding tokens.

#### Scenario: Secret is scoped and retained
- **WHEN** the stack is deployed
- **THEN** the execution role can read only the relay's own Secrets Manager secret and that secret is
  retained on stack deletion

#### Scenario: Network access is least-privilege
- **WHEN** the stack is deployed
- **THEN** the ALB accepts ingress only from the configured Wenrix client CIDR and the tasks accept
  traffic only from the ALB security group

### Requirement: Hardened Helm chart

The relay SHALL ship a Helm chart under `deployment/helm/chart/` with hardened pod/container
security contexts, CPU/memory requests and limits aligned to the perf baseline, an HPA, a PDB,
probes wired to `/liveness` and `/readiness`, and a ServiceMonitor guarded by a values flag. Secrets
SHALL be mounted from Kubernetes Secrets and SHALL NOT appear in ConfigMaps or logs. The chart SHALL
NOT render a NetworkPolicy; deployment-specific ingress and egress restrictions are the customer's
responsibility through cluster or cloud controls such as a customer-managed NetworkPolicy, security
groups, or service-mesh policy.

#### Scenario: Rendered workload is hardened
- **WHEN** the chart is rendered with `helm template`
- **THEN** the Deployment sets non-root, read-only-root-filesystem, dropped capabilities, and seccomp
  `RuntimeDefault`, wires liveness/readiness probes, and renders no plaintext secret into the ConfigMap

#### Scenario: Chart emits no NetworkPolicy
- **WHEN** the chart is rendered with any supported values
- **THEN** no Kubernetes NetworkPolicy resource is emitted

### Requirement: PII key provisioning survives upgrade
The chart SHALL provision the PII master-key Secret create-if-absent and SHALL NOT
regenerate it on `helm upgrade`; all pods SHALL mount the same Secret at the keyring file
path wired to `RELAY_PII_KEYRING_FILE`. The generated Secret SHALL contain a single
base64(32-byte) master key and SHALL NOT reference key epochs or an active-epoch value.

#### Scenario: Upgrade does not regenerate the key
- **WHEN** the chart is upgraded and a master-key Secret already exists
- **THEN** the existing Secret is preserved and no new master key is generated

#### Scenario: Rendered Secret carries no epoch fields
- **WHEN** the chart is rendered with `helm template`
- **THEN** neither the Secret nor the Deployment references `RELAY_PII_KEY_EPOCH_ACTIVE` or
  a `piiKeyring.activeEpoch` value

### Requirement: Tagged release pipeline
A `release.yml` workflow SHALL run on tags matching `v*` and SHALL derive the semver, build and push
the Alpine image to GHCR, generate an SBOM with syft, optionally cosign-sign the image, publish a
GitHub Release with a Conventional Commits changelog, and bump the Helm chart `appVersion`. The
workflow SHALL use least-privilege permissions.

#### Scenario: Release on tag
- **WHEN** a `v*` tag is pushed
- **THEN** the workflow builds and pushes the image to GHCR, attaches an SBOM, and publishes a
  GitHub Release for the derived version

### Requirement: Load and performance harness

The repository SHALL provide a k6 load/perf harness covering pass-through, structural
credential-swap, PII-redaction, and redaction-plus-de-anonymization round-trip scenarios across an
explicit 2KB/32KB/256KB payload matrix with ramped virtual users, reporting p50/p95/p99 latency and
error rate against a fixed mock-upstream latency. Before load generation, a semantic preflight SHALL
prove that each scenario executed its intended pipeline stages: the swap case structurally replaces
Travelfusion credentials, the redaction case receives XML and rewrites PII, and round-trip uses a
valid token generated by the configured test keyring and restores its plaintext. CI SHALL publish
uniquely named per-size summary artifacts and SHALL be non-gating by default.

#### Scenario: Perf preflight proves four paths
- **WHEN** the performance job starts
- **THEN** pass-through, credential swap, XML redaction, and valid-token de-anonymization are verified
  before k6 load begins

#### Scenario: Perf CI covers the payload matrix
- **WHEN** the performance workflow runs
- **THEN** it executes 2KB, 32KB, and 256KB variants and publishes a unique artifact for each size

#### Scenario: Perf results are non-gating
- **WHEN** latency or error-rate thresholds are exceeded
- **THEN** the results remain available as artifacts without failing the default build gate
