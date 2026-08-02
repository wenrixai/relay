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
      RelayConfigJson='{"channels":[{"name":"travelport","type":"travelport"}]}' \
      BasicAuthEnabled=true \
      BasicAuthUser=wenrix \
      BasicAuthPass='replace-with-a-strong-password'
```

`BasicAuthUser`/`BasicAuthPass` are required whenever `BasicAuthEnabled=true` (the app crash-loops on
startup without them); a template `Rule` enforces this at deploy time. Both parameters are `NoEcho` and
are written into a dedicated `${AWS::StackName}/basic-auth` Secrets Manager secret — the relay task
reads `RELAY_BASIC_AUTH_USER`/`RELAY_BASIC_AUTH_PASS` from that secret, never from a plaintext
container environment variable. Set `BasicAuthEnabled=false` (and leave the user/pass params empty) to
disable basic auth entirely.

`RelayConfigJson` is `NoEcho` too. In this deployment it must **not** carry channel credentials — there
is no credential-swap secret wired up for it, so any secret placed there would be visible in the task
definition's environment variables (Secrets Manager values only cover the PII keyring and basic auth).
Keep channel credentials out of `RelayConfigJson` until a dedicated secret-backed credential path is
added.

Set the keyring after the stack exists (the secret is created empty and **retained** on delete):

```bash
aws secretsmanager put-secret-value \
  --secret-id wenrix-relay/pii-keyring \
  --secret-string "$(head -c32 /dev/urandom | base64)"
```

## Security posture

- Tasks run in **private subnets**, non-root, **read-only root filesystem** (writable `/tmp` only).
- ALB ingress limited to `WenrixIngressCidr`; tasks accept traffic **only from the ALB** SG.
- PII keyring in **Secrets Manager**; secret has `DeletionPolicy: Retain` so stack deletion never
  orphans outstanding tokens.
- Basic auth credentials (when enabled) also live in **Secrets Manager**, injected into the container
  via ECS `Secrets` (never a plaintext environment variable).
- The execution role's `read-relay-secrets` inline policy grants `secretsmanager:GetSecretValue` on
  only the PII keyring secret, plus the basic-auth secret when `BasicAuthEnabled=true`.
- Public subnets do **not** auto-assign public IPs; only the ALB and NAT gateway live there.
- The ALB SG egresses **only to the task SG** on `ContainerPort`.

### Encryption at rest

By default the stack creates a customer-managed KMS key (`alias/<stack-name>`) with rotation
enabled and uses it for both Secrets Manager secrets and the CloudWatch log group. Like the PII
keyring secret, the key is `Retain`-on-delete — deleting the stack must never leave the keyring
undecryptable. The key policy delegates administration to the account root and grants
`logs.<region>.amazonaws.com` encrypt access scoped by encryption context to this stack's log group.
The execution role gets a separate `decrypt-relay-secrets` policy with `kms:Decrypt` restricted to
`kms:ViaService = secretsmanager.<region>.amazonaws.com`.

- `KmsKeyArn` — reuse an existing key instead. Its policy must grant CloudWatch Logs the same
  access, or the log group will fail to create.
- `CreateKmsKey=false` (with an empty `KmsKeyArn`) — fall back to the AWS-managed keys.

A customer-managed key costs roughly $1/month plus request charges.

### Load balancer exposure

`LoadBalancerScheme` defaults to `internet-facing`: the Wenrix client calls the relay from outside
this VPC. Exposure is bounded by `WenrixIngressCidr`, the HTTPS-only listener, and the relay's own
basic auth. Set it to `internal` for deployments fronted by a VPN, Direct Connect, or PrivateLink —
the ALB then moves to the private subnets automatically.

The **task** security group keeps open egress: the relay dials supplier channels whose endpoints are
operator-configured in `RelayConfigJson` and unknowable at deploy time. Narrow it to your channels'
CIDRs if you know them. Both of these are recorded as scanner ignores in the repo's `/.snyk`.

## Single-NAT caveat

This template provisions a **single NAT gateway** (in `PublicSubnet1`) shared by both private subnets.
That NAT gateway — and its AZ — is an egress single point of failure: if `PublicSubnet1`'s AZ has an
outage, tasks in *both* private subnets lose outbound internet access (pulling images, reaching AWS
APIs via the internet, calling out to channels that aren't reachable via VPC endpoints), even though
the ECS service itself is still multi-AZ for inbound/ALB traffic. This is an accepted cost tradeoff (a
second NAT gateway roughly doubles the NAT hourly + data-processing cost) rather than an oversight.

To remove the SPOF, add a second NAT gateway plus a per-AZ private route table:

1. Add a second EIP (`NatEip2`) and a second `AWS::EC2::NatGateway` (`NatGateway2`) in `PublicSubnet2`.
2. Add a second private route table (`PrivateRouteTable2`) with a default route
   (`0.0.0.0/0`) via `NatGateway2`.
3. Point `PrivateSubnet2RouteAssoc` at `PrivateRouteTable2` instead of the shared `PrivateRouteTable`
   (leave `PrivateSubnet1RouteAssoc` on the original table with `NatGateway`).

This keeps each private subnet's egress path confined to its own AZ, at the cost of a second NAT
gateway.

## Validate

```bash
cfn-lint deployment/cloudformation/wenrix-relay.yaml
aws cloudformation validate-template --template-body file://deployment/cloudformation/wenrix-relay.yaml
```

Parameters mirror the Terraform variables (`ImageUri`, `WenrixIngressCidr`, `CertificateArn`,
`RelayConfigJson`, `BasicAuthEnabled`, `BasicAuthUser`, `BasicAuthPass`,
`DesiredCount`, `Min/MaxCapacity`, `VpcCidr`, `LoadBalancerScheme`, `CreateKmsKey`, `KmsKeyArn`, …).

`tests/deployment/test_iac_templates.py` asserts the hardened defaults of both this template and
the Terraform module; it needs no AWS credentials and runs in the normal suite.
