# Tasks — protect the PII keyring secret from Terraform overwrite

## 1. Failing tests first (TDD)

- [x] 1.1 `tests/deployment/`: assert `aws_secretsmanager_secret_version.pii_keyring` and `.basic_auth` both declare `lifecycle { ignore_changes = [secret_string] }` (static HCL parse / plan assertion, consistent with `test_helm_chart.py` style — no live AWS).
- [x] 1.2 `tests/deployment/`: assert the basic-auth-credentials guard is a hard-failing construct (variable `validation` or `lifecycle.precondition`), not a `check` block.

## 2. Secret lifecycle

- [x] 2.1 Add `lifecycle { ignore_changes = [secret_string] }` to `aws_secretsmanager_secret_version.pii_keyring` (main.tf).
- [x] 2.2 Add the same to `aws_secretsmanager_secret_version.basic_auth`.

## 3. Hard-fail on missing credentials

- [x] 3.1 Replace `check "basic_auth_credentials_present"` with a `variable` `validation` block or a `lifecycle.precondition` on `aws_ecs_task_definition` that halts `apply`.

## 4. Docs

- [x] 4.1 `deployment/terraform/README.md`: correct the (false) claim that `check` fails plan/apply; document the one-time out-of-band `put-secret-value` seed flow and key-rotation procedure.

## 5. Verify

- [x] 5.1 `terraform validate` (and `terraform plan` against the example tfvars if runnable in CI) green.
- [x] 5.2 Deployment assertion suite green; `just ci` unaffected.
