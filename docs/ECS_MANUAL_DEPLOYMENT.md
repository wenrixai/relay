# Manual AWS ECS Deployment

This guide deploys the Wenrix Channel Relay to Amazon ECS with the AWS CLI. It is intentionally
small and follows the test configuration in `deployment/helm/chart/values-test.yaml`: one relay
task, public GHCR image, Sabre and Amadeus defaults, Basic Auth disabled, PII disabled, telemetry
metrics disabled, and no autoscaling.

The same task definition works with either:

- **AWS Fargate**, which requires no customer-managed container instances.
- **ECS on EC2**, using Linux container instances already registered with the ECS cluster.

For a production deployment with automated scaling and alarms, use `deployment/terraform/` or
`deployment/cloudformation/`.

## Prerequisites

- AWS CLI v2 and `jq`.
- An authenticated AWS CLI session with permission to create the resources below.
- An existing VPC with two subnets for relay tasks and two subnets for the internet-facing ALB.
- Outbound HTTPS access from the relay-task subnets to GHCR and the configured upstream services.
- An ACM certificate in the deployment Region.
- For ECS on EC2, an existing ECS cluster with compatible Linux container instances and available
  CPU, memory, and ENI capacity. The ECS agent must support `awsvpc` and `awslogs`; when the task
  execution role supplies the log permissions, set `ECS_ENABLE_AWSLOGS_EXECUTIONROLE_OVERRIDE=true`
  in `/etc/ecs/ecs.config` and restart the agent.

## 1. Set deployment values

Set these values once. All later AWS CLI commands use `AWS_REGION`, so resources cannot
accidentally be created in a different configured Region.

```bash
export AWS_REGION="eu-west-1"
export AWS_DEFAULT_REGION="$AWS_REGION"
export AWS_PAGER=""

export CLUSTER_NAME="wenrix-relay"
export SERVICE_NAME="wenrix-relay"
export LAUNCH_TYPE="FARGATE" # FARGATE or EC2
export IMAGE="ghcr.io/wenrixai/wenrix-relay:v0.1.0"

export VPC_ID="vpc-0123456789abcdef0"
export TASK_SUBNET_ID_1="subnet-0aaa1111"
export TASK_SUBNET_ID_2="subnet-0bbb2222"
export ALB_SUBNET_ID_1="subnet-0ccc3333"
export ALB_SUBNET_ID_2="subnet-0ddd4444"
export ALLOWED_CLIENT_CIDR="203.0.113.0/24"
export CERTIFICATE_ARN="arn:aws:acm:eu-west-1:111122223333:certificate/REPLACE_ME"
```

Use `LAUNCH_TYPE=EC2` only when `CLUSTER_NAME` already has suitable ECS container instances.
For Fargate, create the cluster if it does not exist:

```bash
aws ecs create-cluster --cluster-name "$CLUSTER_NAME"
```

## 2. Create the relay configuration

Create `relay.json`:

```json
{
  "channels": [
    { "name": "sabre", "type": "sabre" },
    { "name": "amadeus", "type": "amadeus" }
  ]
}
```

Sabre and Amadeus use their built-in production hosts when `host` and `proxy_pass` are omitted.
Other channel types may require one of those fields; see `docs/PROXY_CONFIGURATION_GUIDE.md`.

This setup does not enable PII processing, so it does not require a PII keyring. If PII is enabled
later, configure a valid `RELAY_PII_KEYRING` through the customer's approved secret-delivery
mechanism before starting the service. Keep an installed keyring unchanged.

Validate and compact the configuration for the task definition:

```bash
RELAY_CONFIG_JSON=$(jq -ce . relay.json)
```

## 3. Create the log group and execution role

```bash
aws logs create-log-group --log-group-name /ecs/wenrix-relay
aws logs put-retention-policy \
  --log-group-name /ecs/wenrix-relay \
  --retention-in-days 30

jq -n '{
  Version: "2012-10-17",
  Statement: [{
    Effect: "Allow",
    Principal: {Service: "ecs-tasks.amazonaws.com"},
    Action: "sts:AssumeRole"
  }]
}' > /tmp/wenrix-relay-ecs-trust.json

EXECUTION_ROLE_ARN=$(aws iam create-role \
  --role-name wenrix-relay-execution \
  --assume-role-policy-document file:///tmp/wenrix-relay-ecs-trust.json \
  --query 'Role.Arn' --output text)

aws iam attach-role-policy \
  --role-name wenrix-relay-execution \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
```

The application does not call AWS APIs, so no task role is needed.

## 4. Register the task definition

The task uses `awsvpc` networking for both Fargate and ECS on EC2. The root filesystem is read-only;
the entrypoint writes the non-secret relay configuration to a writable `/tmp` volume.

```bash
jq -n \
  --arg launch_type "$LAUNCH_TYPE" \
  --arg image "$IMAGE" \
  --arg execution_role "$EXECUTION_ROLE_ARN" \
  --arg region "$AWS_REGION" \
  --arg relay_config "$RELAY_CONFIG_JSON" \
  '{
    family: "wenrix-relay",
    requiresCompatibilities: [$launch_type],
    networkMode: "awsvpc",
    cpu: "256",
    memory: "512",
    executionRoleArn: $execution_role,
    volumes: [{name: "tmp"}],
    containerDefinitions: [{
      name: "relay",
      image: $image,
      essential: true,
      user: "100",
      cpu: 256,
      memory: 256,
      readonlyRootFilesystem: true,
      stopTimeout: 120,
      entryPoint: ["/bin/sh", "-c"],
      command: ["printf '\''%s'\'' \"$RELAY_CONFIG_JSON\" > /tmp/relay.json && exec channel-relay"],
      portMappings: [{containerPort: 8080, protocol: "tcp"}],
      environment: [
        {name: "RELAY_CONFIG_FILE", value: "/tmp/relay.json"},
        {name: "RELAY_CONFIG_JSON", value: $relay_config},
        {name: "RELAY_PORT", value: "8080"},
        {name: "RELAY_BASIC_AUTH_ENABLED", value: "false"},
        {name: "RELAY_DEFAULT_CONNECT_TIMEOUT", value: "30"},
        {name: "RELAY_DEFAULT_READ_TIMEOUT", value: "120"},
        {name: "RELAY_MAX_INSPECT_BYTES", value: "8388608"},
        {name: "RELAY_TELEMETRY_METRICS_ENABLED", value: "false"}
      ],
      mountPoints: [{sourceVolume: "tmp", containerPath: "/tmp", readOnly: false}],
      logConfiguration: {
        logDriver: "awslogs",
        options: {
          "awslogs-group": "/ecs/wenrix-relay",
          "awslogs-region": $region,
          "awslogs-stream-prefix": "relay"
        }
      },
      healthCheck: {
        command: ["CMD-SHELL", "wget -q -O- http://127.0.0.1:8080/readiness || exit 1"],
        interval: 30,
        timeout: 5,
        retries: 3,
        startPeriod: 10
      }
    }]
  }' > /tmp/wenrix-relay-task-definition.json

TASK_DEFINITION_ARN=$(aws ecs register-task-definition \
  --cli-input-json file:///tmp/wenrix-relay-task-definition.json \
  --query 'taskDefinition.taskDefinitionArn' --output text)
```

Using `jq` preserves `$RELAY_CONFIG_JSON` for expansion inside the container and safely escapes the
configuration value. No placeholder substitution is required.

## 5. Create security groups, target group, and ALB

```bash
TASK_SG_ID=$(aws ec2 create-security-group \
  --group-name wenrix-relay-task \
  --description "Wenrix relay tasks; ingress only from the ALB" \
  --vpc-id "$VPC_ID" \
  --query GroupId --output text)

ALB_SG_ID=$(aws ec2 create-security-group \
  --group-name wenrix-relay-alb \
  --description "Wenrix relay ALB" \
  --vpc-id "$VPC_ID" \
  --query GroupId --output text)

aws ec2 authorize-security-group-ingress \
  --group-id "$ALB_SG_ID" \
  --protocol tcp --port 443 \
  --cidr "$ALLOWED_CLIENT_CIDR"

aws ec2 authorize-security-group-ingress \
  --group-id "$TASK_SG_ID" \
  --protocol tcp --port 8080 \
  --source-group "$ALB_SG_ID"

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

ALB_ARN=$(aws elbv2 create-load-balancer \
  --name wenrix-relay \
  --type application \
  --subnets "$ALB_SUBNET_ID_1" "$ALB_SUBNET_ID_2" \
  --security-groups "$ALB_SG_ID" \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text)

aws elbv2 modify-load-balancer-attributes \
  --load-balancer-arn "$ALB_ARN" \
  --attributes \
    Key=idle_timeout.timeout_seconds,Value=130 \
    Key=routing.http.drop_invalid_header_fields.enabled,Value=true

aws elbv2 create-listener \
  --load-balancer-arn "$ALB_ARN" \
  --protocol HTTPS --port 443 \
  --ssl-policy ELBSecurityPolicy-TLS13-1-2-Res-PQ-2025-09 \
  --certificates CertificateArn="$CERTIFICATE_ARN" \
  --default-actions Type=forward,TargetGroupArn="$TG_ARN"
```

The `ip` target type is required because the task definition uses `awsvpc`, including when the
tasks run on ECS container instances.

## 6. Create the ECS service

```bash
aws ecs create-service \
  --cluster "$CLUSTER_NAME" \
  --service-name "$SERVICE_NAME" \
  --task-definition "$TASK_DEFINITION_ARN" \
  --desired-count 1 \
  --launch-type "$LAUNCH_TYPE" \
  --deployment-configuration '{
    "deploymentCircuitBreaker": {"enable": true, "rollback": true},
    "minimumHealthyPercent": 100,
    "maximumPercent": 200
  }' \
  --health-check-grace-period-seconds 60 \
  --network-configuration "awsvpcConfiguration={subnets=[$TASK_SUBNET_ID_1,$TASK_SUBNET_ID_2],securityGroups=[$TASK_SG_ID],assignPublicIp=DISABLED}" \
  --load-balancers "targetGroupArn=$TG_ARN,containerName=relay,containerPort=8080"
```

This creates one task and does not configure autoscaling, matching the Helm test values. Increase
the desired count or add service autoscaling separately when required.

## 7. Verify

```bash
aws ecs wait services-stable \
  --cluster "$CLUSTER_NAME" \
  --services "$SERVICE_NAME"

aws ecs describe-services \
  --cluster "$CLUSTER_NAME" \
  --services "$SERVICE_NAME" \
  --query 'services[0].{rollout:deployments[0].rolloutState,desired:desiredCount,running:runningCount}'

aws elbv2 describe-target-health \
  --target-group-arn "$TG_ARN" \
  --query 'TargetHealthDescriptions[].TargetHealth'

aws logs tail /ecs/wenrix-relay --since 10m
```

Expected results:

- ECS reports `COMPLETED`, with `desired` and `running` both equal to `1`.
- The target reports `healthy`.
- The relay log shows successful startup without configuration errors.

## Console mapping

When using the AWS Console, use the same values from the CLI sections:

- Register a Linux task definition for **Fargate** or **EC2**, using `awsvpc`, 0.25 vCPU, 512 MiB
  task memory, the public GHCR image, a read-only root filesystem, and a writable `/tmp` volume.
- Configure the environment and `/readiness` health check exactly as shown in the generated task
  definition.
- Create an IP target group on port 8080, an HTTPS ALB listener, and security groups that allow
  task ingress only from the ALB.
- Create a one-task replica service with the deployment circuit breaker and 60-second health-check
  grace period.

## See also

- `deployment/helm/chart/values-test.yaml` — equivalent minimal Helm test configuration.
- `deployment/terraform/` — automated ECS Fargate deployment with production controls.
- `deployment/cloudformation/` — automated ECS Fargate deployment with production controls.
- `docs/PROXY_CONFIGURATION_GUIDE.md` — channel and process configuration reference.
