# Protect the PII keyring secret from Terraform overwrite

## Why

`deployment-ci` requires the PII master keyring to be sourced from AWS Secrets Manager and retained on
stack deletion so outstanding `ENC_` tokens are never orphaned; the Helm path already guarantees the
key is created-if-absent and **never regenerated on upgrade**. The Terraform path has no equivalent
guarantee on **update**:

- `deployment/terraform/main.tf` binds `aws_secretsmanager_secret_version.pii_keyring` `secret_string`
  directly to `var.pii_keyring_json` (default `""` → `"{}"`), with no
  `lifecycle { ignore_changes = [secret_string] }`.
- Any routine `terraform apply` that does not re-export `TF_VAR_pii_keyring_json` — a CI pipeline
  bumping `desired_count`, or an operator who forgets the env var — diffs the live secret back to
  `"{}"` and **overwrites the master key**, instantly orphaning every outstanding token (all
  previously issued `ENC_` values become undecryptable → whole-value tokens 502, redaction breaks).
- The same pattern applies to `aws_secretsmanager_secret_version.basic_auth`.

The CloudFormation path is safe (it writes `SecretString: "{}"` once and documents out-of-band
`put-secret-value`), so this is a Terraform-specific gap that contradicts the never-orphan intent of
the spec.

Separately, the Terraform `check "basic_auth_credentials_present"` block only emits a **warning** —
`check` blocks never block `plan`/`apply` — so the comment and README claim that it "fails
plan/apply early" is wrong; a misconfigured apply exits 0 and the task crash-loops in prod.

## What Changes

- Add `lifecycle { ignore_changes = [secret_string] }` to both
  `aws_secretsmanager_secret_version.pii_keyring` and `aws_secretsmanager_secret_version.basic_auth`,
  so Terraform seeds the secret once and never overwrites an operator-managed value on later applies.
  Document the out-of-band `put-secret-value` seed flow (mirroring CloudFormation).
- Replace the ineffective `check` block with a mechanism that actually halts apply on missing
  basic-auth credentials (a `variable` `validation` block or a `lifecycle.precondition` on the task
  definition), and correct the README.

## Capabilities

### Modified Capabilities
- `deployment-ci`: the AWS IaC secret guarantee extends from retain-on-delete to
  **never-overwrite-on-update** for the keyring (and basic-auth) secret, matching the Helm
  never-regenerate guarantee; misconfiguration halts apply rather than warning.

## Impact

- `deployment/terraform/main.tf`: `ignore_changes` on both secret versions; replace `check` with a
  hard-failing validation/precondition.
- `deployment/terraform/README.md`: correct the `check` claim; document the seed flow.
- `tests/deployment/`: assert the `ignore_changes` lifecycle is present on both secret versions
  (static HCL/plan assertion consistent with the existing helm-chart assertion tests).
