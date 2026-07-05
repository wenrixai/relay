# Terraform — Wenrix Relay on ECS Fargate (T5.5)

Provisions a highly available ECS Fargate deployment of the relay on AWS: multi-AZ VPC, HTTPS ALB
(health check `/readiness`), ECS service (min 2 tasks across AZs) with CPU + request autoscaling,
Secrets Manager for the PII keyring, least-privilege IAM/security groups, and CloudWatch logs.

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

- One NAT gateway is used for cost. For zero-egress-SPOF, add one NAT gateway per AZ.
- `terraform validate` runs offline; `plan`/`apply` require AWS credentials.
- Consider `tflint`/`checkov` in CI for deeper policy checks.
