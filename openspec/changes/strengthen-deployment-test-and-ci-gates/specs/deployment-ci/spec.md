## MODIFIED Requirements

### Requirement: CI pipeline
CI SHALL run, on every push/PR, `uv sync --frozen` → ruff lint → `ruff format --check` → mypy strict
→ pylint → pytest (timeout + coverage gate) → image build → `/readiness` smoke, failing fast with no
retries. The image build/push gate SHALL NOT proceed on a **skipped** test job: a change that touches
`Dockerfile*`, `deployment/**`, or workflow files SHALL still run the test gate (or the image/push
jobs SHALL depend on `test` having **succeeded**, not merely "not failed"), so no image is built or
pushed without the test and `/readiness` smoke having run in that same gate.

#### Scenario: CI enforces the full gate
- **WHEN** a change is pushed
- **THEN** CI runs the full lint/type/test/build/smoke pipeline and fails on any step

#### Scenario: Deployment-only change still gates on tests
- **WHEN** a PR touches only `Dockerfile*` or `deployment/**` (no `src/` change)
- **THEN** the image is not built or pushed unless the test job ran and succeeded

### Requirement: PII key provisioning survives upgrade
The chart SHALL provision the PII master-key Secret create-if-absent and SHALL NOT regenerate it on
`helm upgrade`; all pods SHALL mount the same Secret at the keyring file path wired to
`RELAY_PII_KEYRING_FILE`. Epoch rotation SHALL be documented (add a new epoch to the keyring, set
`RELAY_PII_KEY_EPOCH_ACTIVE`, retain prior epochs for decryption). This guarantee SHALL be verified by
a behavioral test — an install-then-upgrade against a real (kind/k3d) cluster asserting the existing
Secret is preserved — not solely by a static template text assertion (which cannot exercise
`helm lookup`). The behavioral test MAY be gated to a manual/nightly workflow to keep the default
suite fast.

#### Scenario: Upgrade does not regenerate the key
- **WHEN** the chart is upgraded and a master-key Secret already exists
- **THEN** the existing Secret is preserved and no new master key is generated

#### Scenario: Behavioral upgrade test exists
- **WHEN** the deployment test suite runs in its upgrade-capable mode
- **THEN** it installs the chart, upgrades it, and asserts the master-key Secret value is unchanged
