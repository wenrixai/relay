## ADDED Requirements

### Requirement: AWS ECS Fargate infrastructure-as-code
The repository SHALL provide two equivalent, self-contained IaC paths — Terraform under
`deployment/terraform/` and CloudFormation under `deployment/cloudformation/` — that deploy the relay
as a highly available ECS Fargate service. Each SHALL provision a multi-AZ VPC (public subnets for the
load balancer, private subnets with NAT egress for tasks), an ALB whose target group health check
targets `/readiness`, an ECS service with at least two tasks spread across availability zones and
autoscaling on CPU or request count, and CloudWatch logging. Task containers SHALL run non-root with a
read-only root filesystem.

#### Scenario: Terraform configuration is valid
- **WHEN** `terraform init && terraform validate` runs against `deployment/terraform/`
- **THEN** the configuration validates without error

#### Scenario: CloudFormation template is valid
- **WHEN** the CloudFormation template is linted
- **THEN** it passes `cfn-lint` and describes a multi-AZ ECS Fargate service

### Requirement: AWS deployment secret and network hardening
The AWS IaC SHALL source the PII master keyring from AWS Secrets Manager (encrypted at rest, never in
plaintext) and inject it into the task as `RELAY_PII_KEYRING`; the task execution role SHALL be scoped
to read only that secret. ALB ingress SHALL be restricted to a configurable Wenrix client CIDR, and the
task security group SHALL accept traffic only from the ALB security group. The secret SHALL carry a
retain-on-delete policy so stack deletion never orphans outstanding tokens.

#### Scenario: Secret is scoped and retained
- **WHEN** the stack is deployed
- **THEN** the execution role can read only the relay's own Secrets Manager secret and that secret is
  retained on stack deletion

#### Scenario: Network access is least-privilege
- **WHEN** the stack is deployed
- **THEN** the ALB accepts ingress only from the configured Wenrix client CIDR and the tasks accept
  traffic only from the ALB security group
