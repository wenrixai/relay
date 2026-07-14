## MODIFIED Requirements

### Requirement: Hardened Helm chart
The relay SHALL ship a Helm chart under `deployment/helm/chart/` that is secure-by-default: pod and
container `securityContext` with `runAsNonRoot: true`, a non-root UID, `readOnlyRootFilesystem: true`
(with writable `emptyDir` only where needed), `allowPrivilegeEscalation: false`, all capabilities
dropped, and seccomp `RuntimeDefault`; CPU/memory requests and limits aligned to the perf baseline;
an HPA; a PDB; probes wired to `/liveness` and `/readiness`; and a ServiceMonitor guarded by a
values flag. Secrets SHALL be mounted from Kubernetes Secrets and SHALL NOT appear in ConfigMaps or
logs. The chart SHALL NOT ship a NetworkPolicy: network segmentation and TLS termination are
delegated to the customer's cluster and ingress controls, and the chart documentation SHALL state
this. When `basicAuth.enabled` is true, rendering SHALL fail with an actionable error unless
`basicAuth.secretName` is set.

#### Scenario: Rendered workload is hardened
- **WHEN** the chart is rendered with `helm template`
- **THEN** the Deployment sets non-root, read-only-root-filesystem, dropped capabilities, and seccomp
  `RuntimeDefault`, wires liveness/readiness probes, and renders no plaintext secret into the ConfigMap

#### Scenario: No NetworkPolicy is rendered
- **WHEN** the chart is rendered with `helm template`
- **THEN** no NetworkPolicy resource is emitted

#### Scenario: Basic auth requires a secret
- **WHEN** the chart is rendered with `basicAuth.enabled: true` and no `basicAuth.secretName`
- **THEN** rendering fails with an error telling the operator to create and reference the Secret

### Requirement: AWS deployment secret and network hardening
The AWS IaC SHALL source the PII master keyring from AWS Secrets Manager (encrypted at rest, never in
plaintext) and inject it into the task as `RELAY_PII_KEYRING`; basic-auth credentials SHALL likewise
be sourced from Secrets Manager and injected via the ECS `secrets` mechanism as
`RELAY_BASIC_AUTH_USER`/`RELAY_BASIC_AUTH_PASS`, never as plaintext environment entries. The task
execution role SHALL be scoped to read only the relay's own secrets. The channel-config JSON input
SHALL be marked sensitive (`sensitive = true` in Terraform, `NoEcho` in CloudFormation); its
delivery as a container environment variable is an accepted design decision. ALB ingress SHALL be
restricted to a configurable Wenrix client CIDR, and the task security group SHALL accept traffic
only from the ALB security group. The ALB idle timeout SHALL exceed the relay's maximum upstream
read timeout. ECS services SHALL enable the deployment circuit breaker with rollback and define a
container stop timeout that covers in-flight upstream calls. The secret SHALL carry a
retain-on-delete policy so stack deletion never orphans outstanding tokens.

#### Scenario: Secret is scoped and retained
- **WHEN** the stack is deployed
- **THEN** the execution role can read only the relay's own Secrets Manager secrets and the keyring
  secret is retained on stack deletion

#### Scenario: Network access is least-privilege
- **WHEN** the stack is deployed
- **THEN** the ALB accepts ingress only from the configured Wenrix client CIDR and the tasks accept
  traffic only from the ALB security group

#### Scenario: Basic auth credentials never appear in plaintext task definitions
- **WHEN** the stack is deployed with basic auth enabled
- **THEN** `RELAY_BASIC_AUTH_USER`/`RELAY_BASIC_AUTH_PASS` are injected via the ECS `secrets`
  mechanism from Secrets Manager and do not appear as plaintext environment values

#### Scenario: Bad deploys roll back automatically
- **WHEN** a deployment produces tasks that repeatedly fail to become healthy
- **THEN** the ECS deployment circuit breaker rolls the service back to the last healthy deployment
