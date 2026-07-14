## MODIFIED Requirements

### Requirement: AWS deployment secret and network hardening
The AWS IaC SHALL source the PII master keyring from AWS Secrets Manager (encrypted at rest, never in
plaintext) and inject it into the task as `RELAY_PII_KEYRING`; the task execution role SHALL be scoped
to read only that secret. ALB ingress SHALL be restricted to a configurable Wenrix client CIDR, and the
task security group SHALL accept traffic only from the ALB security group. The secret SHALL carry a
retain-on-delete policy so stack deletion never orphans outstanding tokens.

The IaC SHALL additionally guarantee that a routine `apply`/update NEVER overwrites or regenerates the
value of the PII keyring secret (nor the basic-auth secret) — matching the Helm chart's
never-regenerate-on-upgrade guarantee. The secret value is seeded once and thereafter managed
out-of-band; subsequent applies that do not intend to rotate the key SHALL leave the live value
untouched, so infrastructure changes (e.g. scaling the service) can never orphan outstanding tokens.
When required client-auth credentials are absent, the IaC SHALL halt `apply` with an error rather than
proceed with only a non-blocking warning.

#### Scenario: Secret is scoped and retained
- **WHEN** the stack is deployed
- **THEN** the execution role can read only the relay's own Secrets Manager secret and that secret is
  retained on stack deletion

#### Scenario: Network access is least-privilege
- **WHEN** the stack is deployed
- **THEN** the ALB accepts ingress only from the configured Wenrix client CIDR and the tasks accept
  traffic only from the ALB security group

#### Scenario: Update never overwrites the keyring value
- **WHEN** a routine `apply`/update runs without an explicit key-rotation input
- **THEN** the live PII keyring secret value is left unchanged and outstanding tokens remain
  decryptable

#### Scenario: Missing client-auth credentials halt apply
- **WHEN** basic auth is enabled but the username/password inputs are empty
- **THEN** `apply` fails with an error and provisions nothing (not a non-blocking warning)
