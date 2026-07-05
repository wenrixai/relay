# Proposal: aws-iac

## Why

Operators want to run the relay on AWS without standing up Kubernetes. The existing artifacts cover
containers (Dockerfile) and Kubernetes (Helm, see `slice-5-hardened-deploy`) but nothing provisions
AWS infrastructure. This change adds two equivalent, self-contained Infrastructure-as-Code paths —
Terraform and CloudFormation — that deploy the relay as a highly available ECS Fargate service, plus
a `.dockerignore` to tighten image builds. This is net-new scope not previously in `docs/PROJECT.md`;
it adds tasks T5.5 and T5.6 to Slice 5.

## What Changes

- Add `deployment/terraform/` (T5.5): an ECS Fargate module — VPC across 2–3 AZs (public subnets for
  the ALB, private subnets + NAT for tasks), an HTTPS ALB with a `/readiness` health check, an ECS
  cluster + hardened task definition + service (min 2 tasks, multi-AZ) with CPU/request autoscaling,
  a Secrets Manager secret for the PII keyring injected as `RELAY_PII_KEYRING`, least-privilege IAM
  and security groups, and CloudWatch logs.
- Add `deployment/cloudformation/wenrix-relay.yaml` (T5.6): the same HA ECS Fargate topology as a
  CloudFormation template with parameters, outputs, least-privilege IAM, Secrets Manager, and a
  `Retain` deletion policy on the secret.
- Add `.dockerignore` to shrink the build context (exclude tests, docs, VCS, caches, IaC).
- Add T5.5/T5.6 to `docs/OpenSpec task lists`.

## Impact

- Deployment: new `deployment/terraform/` and `deployment/cloudformation/`; new `.dockerignore`.
- Config: both stacks wire existing `RELAY_*` env and the PII keyring from Secrets Manager; channel
  config JSON is supplied via the container image or an operator-provided source (documented).
- Security: tasks run in private subnets, non-root with read-only root filesystem; ALB ingress is
  restricted to a configurable Wenrix client CIDR; task security group accepts traffic only from the
  ALB; IAM is scoped so the execution role reads only its own secret; secrets are encrypted at rest
  and never placed in plaintext.
- Docs: `deployment/terraform/README.md` and `deployment/cloudformation/README.md`.
