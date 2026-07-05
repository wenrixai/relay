# CloudFormation — Wenrix Relay on ECS Fargate (T5.6)

`wenrix-relay.yaml` deploys the same highly available ECS Fargate topology as the Terraform module:
multi-AZ VPC, HTTPS ALB (health check `/readiness`), ECS service (min 2 tasks across two AZs) with
CPU + request autoscaling, Secrets Manager for the PII keyring, least-privilege IAM/security groups,
and CloudWatch logs.

## Deploy

```bash
aws cloudformation deploy \
  --stack-name wenrix-relay \
  --template-file deployment/cloudformation/wenrix-relay.yaml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
      ImageUri=ghcr.io/wenrixai/wenrix-relay:v0.1.0 \
      WenrixIngressCidr=203.0.113.0/24 \
      CertificateArn=arn:aws:acm:eu-west-1:111122223333:certificate/xxxx \
      RelayConfigJson='{"channels":[{"name":"travelport","type":"travelport"}]}'
```

Set the keyring after the stack exists (the secret is created empty and **retained** on delete):

```bash
aws secretsmanager put-secret-value \
  --secret-id wenrix-relay/pii-keyring \
  --secret-string '{"0":"'"$(head -c32 /dev/urandom | base64)"'"}'
```

## Security posture

- Tasks run in **private subnets**, non-root, **read-only root filesystem** (writable `/tmp` only).
- ALB ingress limited to `WenrixIngressCidr`; tasks accept traffic **only from the ALB** SG.
- PII keyring in **Secrets Manager**; execution role reads **only that secret**; secret has
  `DeletionPolicy: Retain` so stack deletion never orphans outstanding tokens.

## Validate

```bash
cfn-lint deployment/cloudformation/wenrix-relay.yaml
aws cloudformation validate-template --template-body file://deployment/cloudformation/wenrix-relay.yaml
```

Parameters mirror the Terraform variables (`ImageUri`, `WenrixIngressCidr`, `CertificateArn`,
`RelayConfigJson`, `PiiKeyEpochActive`, `DesiredCount`, `Min/MaxCapacity`, `VpcCidr`, …).
