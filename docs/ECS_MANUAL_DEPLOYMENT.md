# Manual AWS ECS Deployment (No Terraform / CloudFormation)

This guide is for customers who want to deploy the Wenrix Channel Relay on AWS ECS Fargate using
the AWS CLI directly, without adopting the Terraform module or CloudFormation stack. It produces
the same topology as those automated options: a private ECS Fargate service behind an HTTPS ALB,
config delivered as a non-secret environment variable, and secrets sourced from AWS Secrets
Manager.

If you can adopt one of the automated paths, prefer it — it encodes the same hardening with far
less manual work:

- `deployment/terraform/` — Terraform module.
- `deployment/cloudformation/` — CloudFormation template.

For the channel configuration schema itself (channel types, PII modes, authorization, process
settings), see `docs/PROXY_CONFIGURATION_GUIDE.md`.

> **Scope note:** the configuration JSON used in this guide carries no secrets — no channel
> `credentials` block, no credential values of any kind. Channel credential swap is out of scope
> for this manual walkthrough; if your deployment needs it, follow the credential guidance in
> `docs/PROXY_CONFIGURATION_GUIDE.md` and inject those values the same way this guide injects
> basic-auth credentials (Secrets Manager, never the config JSON).

## Prerequisites

- An existing VPC with at least two private subnets (for the ECS tasks) and a route to a NAT
  gateway or NAT instance for outbound internet access (channel APIs, DNS). Public subnets are
  only needed for the ALB.
- The relay container image accessible from the account/region you deploy into (a public registry
  reference, or a private registry with pull credentials configured separately).
- AWS CLI v2, authenticated with permissions to create the resources below.
- An ACM certificate for the HTTPS listener, in the same region as the ALB.

Throughout, replace the placeholder values (`REGION`, `VPC_ID`, subnet IDs, security group IDs,
account ID, CIDRs, certificate ARN, image reference) with your own.

## Primary path: AWS CLI

### 1. CloudWatch log group

```bash
aws logs create-log-group \
  --log-group-name /ecs/wenrix-relay \
  --region "$REGION"

aws logs put-retention-policy \
  --log-group-name /ecs/wenrix-relay \
  --retention-in-days 30 \
  --region "$REGION"
```

### 2. Secrets Manager secrets

Basic-auth credentials (`user` / `pass` keys — the relay reads these via ECS `secrets`, not the
config JSON):

```bash
aws secretsmanager create-secret \
  --name wenrix-relay/basic-auth \
  --description "Wenrix relay basic-auth credentials" \
  --secret-string '{"user":"CHANGE_ME_USER","pass":"CHANGE_ME_PASSWORD"}' \
  --region "$REGION"
```

PII keyring (`{"<epoch>": "<base64(32 random bytes)>"}`; generate a real key rather than reusing
this example):

```bash
KEYRING_JSON=$(printf '{"0":"%s"}' "$(head -c32 /dev/urandom | base64)")

aws secretsmanager create-secret \
  --name wenrix-relay/pii-keyring \
  --description "Wenrix relay PII master keyring — never regenerate while tokens are outstanding" \
  --secret-string "$KEYRING_JSON" \
  --region "$REGION"
```

Note the two secret ARNs returned (`BASIC_AUTH_SECRET_ARN`, `PII_KEYRING_SECRET_ARN`); the IAM
policy below is scoped to exactly these two.

### 3. IAM roles

Execution role (assumed by ECS to pull the image, write logs, and resolve secrets):

```bash
cat > /tmp/ecs-trust-policy.json <<'JSON'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "ecs-tasks.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
JSON

aws iam create-role \
  --role-name wenrix-relay-execution \
  --assume-role-policy-document file:///tmp/ecs-trust-policy.json

aws iam attach-role-policy \
  --role-name wenrix-relay-execution \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

cat > /tmp/ecs-secret-read-policy.json <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": [
        "$BASIC_AUTH_SECRET_ARN",
        "$PII_KEYRING_SECRET_ARN"
      ]
    }
  ]
}
JSON

aws iam put-role-policy \
  --role-name wenrix-relay-execution \
  --policy-name wenrix-relay-secret-read \
  --policy-document file:///tmp/ecs-secret-read-policy.json
```

Task role — the relay makes no AWS API calls at runtime, so this role stays empty (kept only
because ECS requires a task role reference for least-privilege posture, not because the app uses
it):

```bash
aws iam create-role \
  --role-name wenrix-relay-task \
  --assume-role-policy-document file:///tmp/ecs-trust-policy.json
```

### 4. Task definition

The container config is delivered as the `RELAY_CONFIG_JSON` environment variable and written to
the writable `/tmp` mount at startup (the root filesystem is read-only), via an entrypoint wrapper.
No `credentials` block appears anywhere in this JSON.

```bash
cat > /tmp/wenrix-relay-task-def.json <<JSON
{
  "family": "wenrix-relay",
  "requiresCompatibilities": ["FARGATE"],
  "networkMode": "awsvpc",
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::ACCOUNT_ID:role/wenrix-relay-execution",
  "taskRoleArn": "arn:aws:iam::ACCOUNT_ID:role/wenrix-relay-task",
  "volumes": [
    { "name": "tmp" }
  ],
  "containerDefinitions": [
    {
      "name": "relay",
      "image": "ghcr.io/wenrixai/wenrix-relay:v0.1.0",
      "essential": true,
      "user": "100",
      "readonlyRootFilesystem": true,
      "stopTimeout": 120,
      "entryPoint": ["/bin/sh", "-c"],
      "command": [
        "printf '%s' \"$RELAY_CONFIG_JSON\" > /tmp/relay.json && exec channel-relay"
      ],
      "portMappings": [
        { "containerPort": 8080, "protocol": "tcp" }
      ],
      "environment": [
        { "name": "RELAY_CONFIG_FILE", "value": "/tmp/relay.json" },
        {
          "name": "RELAY_CONFIG_JSON",
          "value": "{\"channels\":[{\"name\":\"sabre-prod\",\"type\":\"sabre\"},{\"name\":\"amadeus-prod\",\"type\":\"amadeus\"}]}"
        },
        { "name": "RELAY_PORT", "value": "8080" },
        { "name": "RELAY_BASIC_AUTH_ENABLED", "value": "true" }
      ],
      "secrets": [
        {
          "name": "RELAY_BASIC_AUTH_USER",
          "valueFrom": "BASIC_AUTH_SECRET_ARN:user::"
        },
        {
          "name": "RELAY_BASIC_AUTH_PASS",
          "valueFrom": "BASIC_AUTH_SECRET_ARN:pass::"
        },
        {
          "name": "RELAY_PII_KEYRING",
          "valueFrom": "PII_KEYRING_SECRET_ARN"
        }
      ],
      "mountPoints": [
        { "sourceVolume": "tmp", "containerPath": "/tmp", "readOnly": false }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/wenrix-relay",
          "awslogs-region": "REGION",
          "awslogs-stream-prefix": "relay"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "wget -q -O- http://127.0.0.1:8080/liveness || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 10
      }
    }
  ]
}
JSON

# Substitute REGION/ACCOUNT_ID/BASIC_AUTH_SECRET_ARN/PII_KEYRING_SECRET_ARN before registering, e.g.:
# sed -i '' \
#   -e "s#REGION#${REGION}#g" \
#   -e "s#ACCOUNT_ID#${ACCOUNT_ID}#g" \
#   -e "s#BASIC_AUTH_SECRET_ARN#${BASIC_AUTH_SECRET_ARN}#g" \
#   -e "s#PII_KEYRING_SECRET_ARN#${PII_KEYRING_SECRET_ARN}#g" \
#   /tmp/wenrix-relay-task-def.json

aws ecs register-task-definition \
  --cli-input-json file:///tmp/wenrix-relay-task-def.json \
  --region "$REGION"
```

Replace `RELAY_CONFIG_JSON`'s value with your actual channel list. Only `name` and `type` are
required per channel; see `docs/PROXY_CONFIGURATION_GUIDE.md` for the full channel schema (hosts,
PII, authorization). Keep credentials out of this value — they do not belong in the config JSON.

### 5. Networking: target group, ALB, security groups

Task security group (ingress only from the ALB security group):

```bash
TASK_SG_ID=$(aws ec2 create-security-group \
  --group-name wenrix-relay-task \
  --description "Wenrix relay tasks — ingress only from the ALB" \
  --vpc-id "$VPC_ID" \
  --query 'GroupId' --output text)
```

ALB security group (ingress from Wenrix/client CIDRs only — never `0.0.0.0/0`):

```bash
ALB_SG_ID=$(aws ec2 create-security-group \
  --group-name wenrix-relay-alb \
  --description "Wenrix relay ALB — ingress from approved client CIDRs" \
  --vpc-id "$VPC_ID" \
  --query 'GroupId' --output text)

aws ec2 authorize-security-group-ingress \
  --group-id "$ALB_SG_ID" \
  --protocol tcp --port 443 \
  --cidr "203.0.113.0/24"

aws ec2 authorize-security-group-ingress \
  --group-id "$TASK_SG_ID" \
  --protocol tcp --port 8080 \
  --source-group "$ALB_SG_ID"
```

Target group (health check against `/readiness`, not `/liveness` — readiness reflects config
validity):

```bash
TG_ARN=$(aws elbv2 create-target-group \
  --name wenrix-relay \
  --protocol HTTP --port 8080 \
  --vpc-id "$VPC_ID" \
  --target-type ip \
  --health-check-path /readiness \
  --healthy-threshold-count 2 \
  --unhealthy-threshold-count 3 \
  --health-check-timeout-seconds 5 \
  --health-check-interval-seconds 15 \
  --matcher HttpCode=200 \
  --query 'TargetGroups[0].TargetGroupArn' --output text)

aws elbv2 modify-target-group-attributes \
  --target-group-arn "$TG_ARN" \
  --attributes Key=deregistration_delay.timeout_seconds,Value=120
```

ALB (idle timeout above the relay's default 120s upstream read timeout) and HTTPS listener:

```bash
ALB_ARN=$(aws elbv2 create-load-balancer \
  --name wenrix-relay \
  --type application \
  --subnets PUBLIC_SUBNET_ID_1 PUBLIC_SUBNET_ID_2 \
  --security-groups "$ALB_SG_ID" \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text)

aws elbv2 modify-load-balancer-attributes \
  --load-balancer-arn "$ALB_ARN" \
  --attributes Key=idle_timeout.timeout_seconds,Value=130

aws elbv2 create-listener \
  --load-balancer-arn "$ALB_ARN" \
  --protocol HTTPS --port 443 \
  --ssl-policy ELBSecurityPolicy-TLS13-1-2-2021-06 \
  --certificates CertificateArn="$CERTIFICATE_ARN" \
  --default-actions Type=forward,TargetGroupArn="$TG_ARN"
```

### 6. ECS cluster and service

```bash
aws ecs create-cluster --cluster-name wenrix-relay --region "$REGION"

aws ecs create-service \
  --cluster wenrix-relay \
  --service-name wenrix-relay \
  --task-definition wenrix-relay \
  --desired-count 2 \
  --launch-type FARGATE \
  --deployment-configuration '{
    "deploymentCircuitBreaker": { "enable": true, "rollback": true },
    "minimumHealthyPercent": 100,
    "maximumPercent": 200
  }' \
  --health-check-grace-period-seconds 60 \
  --network-configuration "awsvpcConfiguration={subnets=[PRIVATE_SUBNET_ID_1,PRIVATE_SUBNET_ID_2],securityGroups=[$TASK_SG_ID],assignPublicIp=DISABLED}" \
  --load-balancers "targetGroupArn=$TG_ARN,containerName=relay,containerPort=8080" \
  --region "$REGION"
```

### 7. Verify

```bash
# Wait for the deployment to stabilize.
aws ecs wait services-stable --cluster wenrix-relay --services wenrix-relay --region "$REGION"

# Confirm the service is reachable through the ALB.
ALB_DNS=$(aws elbv2 describe-load-balancers \
  --load-balancer-arns "$ALB_ARN" \
  --query 'LoadBalancers[0].DNSName' --output text)
curl -sSf "https://$ALB_DNS/liveness"

# Tail recent container logs.
aws logs tail /ecs/wenrix-relay --since 10m --region "$REGION"
```

## Console notes

The same result via the AWS Console, at bullet level (not click-by-click):

- **CloudWatch Logs** → Log groups → create `/ecs/wenrix-relay`, set retention to 30 days.
- **Secrets Manager** → Store a new secret → "Other type of secret" → key/value pairs `user`/`pass`
  for basic-auth; a second secret with a single JSON blob for the PII keyring.
- **IAM** → Roles → create `wenrix-relay-execution` trusted by `ecs-tasks.amazonaws.com`, attach
  the `AmazonECSTaskExecutionRolePolicy` managed policy, add an inline policy granting
  `secretsmanager:GetSecretValue` scoped to the two secret ARNs above. Create an empty
  `wenrix-relay-task` role with the same trust policy and no permissions.
- **ECS** → Task definitions → create new revision, Fargate, 1 vCPU / 2 GB, container user `100`,
  read-only root filesystem on, add a bind mount named `tmp` at `/tmp`, set entry point/command to
  the `printf ... && exec channel-relay` wrapper, set environment variables and secrets as in the
  JSON above, awslogs driver pointed at the log group, stop timeout 120s, container health check
  `wget` against `/liveness`.
- **EC2** → Security Groups → create the ALB SG (ingress 443 from your CIDRs) and the task SG
  (ingress 8080 from the ALB SG only).
- **EC2** → Load Balancers → create an internet-facing ALB in the public subnets with the ALB SG,
  idle timeout 130s; create a target group (HTTP 8080, IP target type, health check `/readiness`,
  matcher 200, deregistration delay 120s); add an HTTPS:443 listener with your ACM certificate
  forwarding to the target group.
- **ECS** → Clusters → create cluster, then create a service on Fargate: desired count 2, private
  subnets, `assignPublicIp` disabled, task SG, attach the load balancer/target group, enable the
  deployment circuit breaker with rollback, health check grace period 60s.
- Confirm rollout under the service's "Deployments" tab, then hit `https://<alb-dns>/liveness` and
  check the CloudWatch log group for startup output.

## See also

- `deployment/terraform/` — automated Terraform module for this same topology.
- `deployment/cloudformation/` — automated CloudFormation template for this same topology.
- `docs/PROXY_CONFIGURATION_GUIDE.md` — channel configuration schema, PII modes, process settings.
