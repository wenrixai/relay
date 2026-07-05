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

Provide the PII keyring out-of-band (never commit it):

```bash
export TF_VAR_pii_keyring_json='{"0":"'"$(head -c32 /dev/urandom | base64)"'"}'
terraform apply
```

## Security posture

- Tasks run in **private subnets** (egress via NAT), non-root (`user = "100"`) with a **read-only
  root filesystem** (writable `/tmp` volume only).
- ALB ingress is limited to `wenrix_ingress_cidrs`; the task security group accepts traffic **only
  from the ALB** security group.
- PII keyring lives in **Secrets Manager**; the ECS execution role can read **only that secret**.
- HTTPS listener uses a TLS 1.3 policy; ALB drops invalid header fields.

## Channel config & secrets

- `relay_config_json` (no secrets) is written to `/tmp/relay.json` at container start and read via
  `RELAY_CONFIG_FILE`. For larger/static config, bake it into a derived image instead.
- `RELAY_PII_KEYRING` is injected from Secrets Manager. Rotate by adding a new epoch to the keyring
  JSON and bumping `pii_key_epoch_active`; keep prior epochs so existing tokens stay decryptable.

## Notes

- `terraform validate` runs offline; `plan`/`apply` require AWS credentials.
- Consider `tflint`/`checkov` in CI for deeper policy checks.
