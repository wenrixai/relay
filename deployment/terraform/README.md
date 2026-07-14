# Terraform — Wenrix Relay on ECS Fargate

Deploys the relay app **into an existing VPC** (this does not create networking): HTTPS ALB
(health check `/readiness`), ECS service (min 2 tasks across AZs) with CPU + request autoscaling,
Secrets Manager for the PII keyring, least-privilege IAM/security groups, and CloudWatch logs.

Bring your own VPC with >= 2 public subnets (for the ALB) and >= 2 private subnets with NAT egress
(for the tasks) across at least 2 AZs, and pass their IDs in via `vpc_id` / `public_subnet_ids` /
`private_subnet_ids`.

## Usage

```bash
cd deployment/terraform
cp terraform.tfvars.example terraform.tfvars   # edit values
terraform init
terraform plan
terraform apply
```

Seed the PII keyring **once**, out-of-band (never commit it):

```bash
export TF_VAR_pii_keyring_json='{"0":"'"$(head -c32 /dev/urandom | base64)"'"}'
terraform apply   # seeds the secret on first create
```

After the initial seed the secret value is managed out-of-band and Terraform **ignores changes to
it** (`lifecycle { ignore_changes = [secret_string] }`). Routine applies — scaling the service, any
run without `TF_VAR_pii_keyring_json` re-exported — will **not** overwrite the live master key, so
outstanding `ENC_` tokens are never orphaned. To rotate, add a new epoch out-of-band:

```bash
aws secretsmanager put-secret-value --secret-id <name>/pii-keyring \
  --secret-string '{"0":"<old>","1":"<new>"}'   # then bump pii_key_epoch_active
```

The basic-auth secret uses the same seed-once / `ignore_changes` treatment.

## Security posture

- Tasks run in **private subnets** (egress via NAT), non-root (`user = "100"`) with a **read-only
  root filesystem** (writable `/tmp` volume only).
- ALB ingress is limited to `wenrix_ingress_cidrs`; the task security group accepts traffic **only
  from the ALB** security group.
- PII keyring lives in **Secrets Manager**; the ECS execution role can read **only that secret**.
- HTTPS listener uses a TLS 1.3 policy; ALB drops invalid header fields.

## Channel config & secrets

- `relay_config_json` is written to `/tmp/relay.json` at container start and read via
  `RELAY_CONFIG_FILE`. This deployment does not use channel credential swap, so the config JSON
  itself carries no secrets — it is still marked `sensitive` in Terraform to avoid it leaking into
  plan/apply output. For larger/static config, bake it into a derived image instead.
- `RELAY_PII_KEYRING` is injected from Secrets Manager. Rotate by adding a new epoch to the keyring
  JSON and bumping `pii_key_epoch_active`; keep prior epochs so existing tokens stay decryptable.
- **Basic auth** (`basic_auth_enabled`, default `true`): the app crash-loops if enabled without
  credentials, so `basic_auth_user` / `basic_auth_pass` are required (non-empty) whenever it's
  enabled — a resource `precondition` on the ECS task definition **halts** `plan`/`apply` with a
  clear error if they're missing (a `check` block only warns and would let apply exit 0).
  When enabled, a `${var.name}/basic-auth` secret (`{"user":...,"pass":...}`) is created in
  Secrets Manager (same recovery-window treatment as the PII keyring) and its `user`/`pass` JSON
  keys are injected as `RELAY_BASIC_AUTH_USER` / `RELAY_BASIC_AUTH_PASS`. Supply the values
  out-of-band (e.g. `TF_VAR_basic_auth_user` / `TF_VAR_basic_auth_pass`); never commit them.
- **Private registry pulls** (`ghcr_credentials_secret_arn`, optional): point this at an existing
  Secrets Manager secret holding `{"username":...,"password":...}` to pull `var.image` from a
  private registry (e.g. GHCR). When set, it's wired in as `repositoryCredentials` on the
  container and the execution role is granted read access to that one secret; when unset, no
  registry credentials are configured.
- **PII rules API** (`rules_api_url`, optional): when set, adds `RELAY_RULES_API_URL` to the
  container environment; when empty, the variable is omitted entirely rather than passed empty.

## Alarming

- `alarm_sns_topic_arn` (optional): SNS topic notified by two CloudWatch alarms created for every
  deployment — ALB `HTTPCode_ELB_5XX_Count` (sum >= 10 over 5 minutes) and target group
  `UnHealthyHostCount` (>= 1, over 2 consecutive 1-minute periods). Alarms exist regardless; when
  this var is empty they simply have no `alarm_actions`/`ok_actions`.

## Deployment safety & timeouts

- ECS deployments use a `deployment_circuit_breaker` (rollback on failure) and a 60s
  `health_check_grace_period_seconds` so a slow-starting task isn't killed before its first health
  check.
- Container `stopTimeout` is 120s and the target group `deregistration_delay` matches it, so
  in-flight requests can drain on deploy/scale-in before the task is force-killed.
- The ALB `idle_timeout` is 130s, kept above the app's 120s upstream read timeout so the ALB never
  cuts a connection the app itself would still be willing to serve.

## Notes

- `terraform validate` runs offline; `plan`/`apply` require AWS credentials.
- Consider `tflint`/`checkov` in CI for deeper policy checks.
- The `task` IAM role intentionally has no attached policies: the relay makes no AWS API calls at
  runtime (config/secrets are injected by the execution role at task startup).
