# Tasks: aws-iac

## 1. Spec

- [x] 1.1 Add OpenSpec delta for deployment-ci (AWS ECS Fargate IaC) and append T5.5/T5.6 to
      the spec tree; `openspec validate --strict`.

## 2. Build context

- [x] 2.1 Add `.dockerignore` (exclude tests, docs, openspec, VCS, caches, IaC); `docker build`
      still succeeds.

## 3. Terraform (T5.5)

- [x] 3.1 Author `deployment/terraform/` (versions, variables, main, outputs, tfvars example):
      VPC/subnets/NAT, ALB + `/readiness` target group, ECS cluster + hardened task def + service
      (min 2, multi-AZ) + autoscaling, Secrets Manager + scoped IAM, least-privilege security groups,
      CloudWatch logs.
- [x] 3.2 `terraform init && terraform validate` clean; `deployment/terraform/README.md`.

## 4. CloudFormation (T5.6)

- [x] 4.1 Author `deployment/cloudformation/wenrix-relay.yaml`: same HA ECS Fargate topology with
      parameters/outputs, scoped IAM, Secrets Manager (`Retain`), autoscaling, ALB `/readiness`.
- [x] 4.2 `cfn-lint` clean; `deployment/cloudformation/README.md`.

## 5. Close-out

- [x] 5.1 Validate templates; pre-commit green.
- [ ] 5.2 Archive OpenSpec change after validation.
