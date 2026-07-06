## ADDED Requirements

### Requirement: Hardened Helm chart
The relay SHALL ship a Helm chart under `deployment/helm/chart/` that is secure-by-default: pod and
container `securityContext` with `runAsNonRoot: true`, a non-root UID, `readOnlyRootFilesystem: true`
(with writable `emptyDir` only where needed), `allowPrivilegeEscalation: false`, all capabilities
dropped, and seccomp `RuntimeDefault`; CPU/memory requests and limits aligned to the perf baseline;
a default-deny NetworkPolicy allowing ingress only from the Wenrix client source and egress only to
configured channel hosts, the telemetry endpoint, and DNS; an HPA; a PDB; probes wired to `/liveness`
and `/readiness`; and a ServiceMonitor guarded by a values flag. Secrets SHALL be mounted from
Kubernetes Secrets and SHALL NOT appear in ConfigMaps or logs.

#### Scenario: Rendered workload is hardened
- **WHEN** the chart is rendered with `helm template`
- **THEN** the Deployment sets non-root, read-only-root-filesystem, dropped capabilities, and seccomp
  `RuntimeDefault`, wires liveness/readiness probes, and renders no plaintext secret into the ConfigMap

#### Scenario: NetworkPolicy restricts egress
- **WHEN** the chart is rendered with channels and a telemetry endpoint configured
- **THEN** a default-deny NetworkPolicy is emitted whose egress allow-list covers only the channel
  hosts, the telemetry endpoint, and DNS

### Requirement: PII key provisioning survives upgrade
The chart SHALL provision the PII master-key Secret create-if-absent and SHALL NOT regenerate it on
`helm upgrade`; all pods SHALL mount the same Secret at the keyring file path wired to
`RELAY_PII_KEYRING_FILE`. Epoch rotation SHALL be documented (add a new epoch to the keyring, set
`RELAY_PII_KEY_EPOCH_ACTIVE`, retain prior epochs for decryption).

#### Scenario: Upgrade does not regenerate the key
- **WHEN** the chart is upgraded and a master-key Secret already exists
- **THEN** the existing Secret is preserved and no new master key is generated

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
The repository SHALL provide a k6 load/perf harness covering pass-through, credential-swap,
PII-redaction, and redaction-plus-de-anonymization round-trip scenarios across a 2KB/32KB/256KB
payload matrix with ramped virtual users, reporting p50/p95/p99 latency and error rate against a
fixed mock-upstream latency. Results SHALL be published as a CI artifact and SHALL be non-gating by
default.

#### Scenario: Perf run produces a non-gating artifact
- **WHEN** the perf harness runs in CI
- **THEN** a summary artifact with per-scenario p50/p95/p99 and error rate is published without
  failing the build
