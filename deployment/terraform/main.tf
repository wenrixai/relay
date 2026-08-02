locals {
  image_tag = var.image

  container_environment = [
    { name = "RELAY_CONFIG_FILE", value = "/tmp/relay.json" },
    { name = "RELAY_CONFIG_JSON", value = var.relay_config_json },
    { name = "RELAY_PORT", value = tostring(var.container_port) },
    { name = "RELAY_BASIC_AUTH_ENABLED", value = tostring(var.basic_auth_enabled) },
    { name = "RELAY_OTLP_ENDPOINT", value = var.otlp_endpoint },
    { name = "RELAY_ROOT_PATH", value = var.context_path },
  ]

  # T1: basic-auth credentials only injected when basic auth is enabled.
  container_secrets = concat(
    [
      { name = "RELAY_PII_KEYRING", valueFrom = aws_secretsmanager_secret.pii_keyring.arn }
    ],
    var.basic_auth_enabled ? [
      { name = "RELAY_BASIC_AUTH_USER", valueFrom = "${aws_secretsmanager_secret.basic_auth[0].arn}:user::" },
      { name = "RELAY_BASIC_AUTH_PASS", valueFrom = "${aws_secretsmanager_secret.basic_auth[0].arn}:pass::" },
    ] : []
  )
}

# T1: basic_auth_enabled implies both credentials are actually set, otherwise the app
# crash-loops on startup. Fail plan/apply early with a clear message.
check "basic_auth_credentials_present" {
  assert {
    condition     = !var.basic_auth_enabled || (var.basic_auth_user != "" && var.basic_auth_pass != "")
    error_message = "basic_auth_enabled = true requires non-empty basic_auth_user and basic_auth_pass (the relay crash-loops without them)."
  }
}

# --- Security groups --------------------------------------------------------

resource "aws_security_group" "alb" {
  name        = "${var.name}-alb"
  description = "ALB ingress from Wenrix client source only."
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTPS from Wenrix client"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = var.wenrix_ingress_cidrs
  }

  # Egress is declared as a standalone rule below so it can reference the task security
  # group without creating a dependency cycle between the two SG resources. Omitting the
  # block here makes Terraform revoke the AWS default allow-all egress rule.

  tags = { Name = "${var.name}-alb" }
}

# The ALB only ever talks to the relay tasks, so scope its egress to exactly that.
resource "aws_vpc_security_group_egress_rule" "alb_to_task" {
  description                  = "To relay tasks"
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_security_group.task.id
  ip_protocol                  = "tcp"
  from_port                    = var.container_port
  to_port                      = var.container_port
}

resource "aws_security_group" "task" {
  name        = "${var.name}-task"
  description = "Relay tasks accept traffic only from the ALB."
  vpc_id      = var.vpc_id

  ingress {
    description     = "From ALB"
    from_port       = var.container_port
    to_port         = var.container_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  # Deliberately open egress (suppressed in /.snyk): the relay dials supplier channels
  # (Sabre, Amadeus, Travelport, Travelfusion, Farelogix, BA/LA NDC) whose endpoints are
  # operator-configured in relay.json and unknowable at deploy time, plus the OTLP
  # collector and DNS. Narrow this to your channels' egress CIDRs if you know them.
  # Tasks are unreachable from outside: private subnets, assign_public_ip = false, and
  # ingress restricted to the ALB security group.
  egress {
    description = "Upstream channels, telemetry, DNS"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.name}-task" }
}

# --- Load balancer ----------------------------------------------------------

# Internet-facing by default (suppressed in /.snyk): the relay is reached by the Wenrix
# client from outside the operator's VPC. Ingress is restricted to wenrix_ingress_cidrs on
# the ALB security group. Set internal_lb = true for VPN/Direct Connect/PrivateLink-fronted
# deployments and pass private subnet IDs in public_subnet_ids.
resource "aws_lb" "this" {
  name               = var.name
  load_balancer_type = "application"
  internal           = var.internal_lb
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids

  drop_invalid_header_fields = true
  enable_deletion_protection = false
  # T8: app upstream read timeout is 120s; keep the ALB idle timeout above it.
  idle_timeout = 130
}

resource "aws_lb_target_group" "this" {
  name        = var.name
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  # T4: let in-flight requests drain for up to the container's stopTimeout before deregistering.
  deregistration_delay = 120

  health_check {
    path                = "/readiness"
    port                = "traffic-port"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 15
    matcher             = "200"
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this.arn
  }
}

# When a context path is configured, add an explicit path rule so the LB routes
# `<context_path>` and `<context_path>/*` to the relay target group. The default action already
# forwards everything, so this rule is documentary/priority-explicit; the relay itself tolerates
# both a forwarded and a stripped prefix (see the context-path middleware).
resource "aws_lb_listener_rule" "context_path" {
  count        = var.context_path == "" ? 0 : 1
  listener_arn = aws_lb_listener.https.arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this.arn
  }

  condition {
    path_pattern {
      values = [var.context_path, "${var.context_path}/*"]
    }
  }
}

# --- Encryption -------------------------------------------------------------

data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

# The log group ARN is built as a string rather than referenced from the resource: the log
# group depends on the key, so referencing it back inside the key policy would be a cycle.
locals {
  log_group_name = "/ecs/${var.name}"
  log_group_arn  = "arn:${data.aws_partition.current.partition}:logs:${var.region}:${data.aws_caller_identity.current.account_id}:log-group:${local.log_group_name}"

  create_kms_key = var.create_kms_key && var.kms_key_arn == ""
  # null (not "") so the argument is omitted entirely and AWS falls back to its managed key.
  kms_key_arn = var.kms_key_arn != "" ? var.kms_key_arn : (local.create_kms_key ? aws_kms_key.this[0].arn : null)
}

data "aws_iam_policy_document" "kms" {
  count = local.create_kms_key ? 1 : 0

  # Without this the key is unmanageable: IAM policies in the account cannot grant access
  # to a key whose own policy does not delegate to the account root.
  statement {
    sid       = "AllowAccountAdministration"
    actions   = ["kms:*"]
    resources = ["*"]

    principals {
      type        = "AWS"
      identifiers = ["arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }

  # CloudWatch Logs encrypts on the service's own behalf, so it needs a direct grant.
  # Scoped by encryption context to this relay's log group only.
  statement {
    sid = "AllowCloudWatchLogs"
    actions = [
      "kms:Encrypt*",
      "kms:Decrypt*",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:Describe*",
    ]
    resources = ["*"]

    principals {
      type        = "Service"
      identifiers = ["logs.${var.region}.amazonaws.com"]
    }

    condition {
      test     = "ArnEquals"
      variable = "kms:EncryptionContext:aws:logs:arn"
      values   = [local.log_group_arn]
    }
  }
}

resource "aws_kms_key" "this" {
  count = local.create_kms_key ? 1 : 0

  description             = "Encrypts the Wenrix relay's Secrets Manager secrets and CloudWatch logs."
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.kms[0].json
}

resource "aws_kms_alias" "this" {
  count = local.create_kms_key ? 1 : 0

  name          = "alias/${var.name}"
  target_key_id = aws_kms_key.this[0].key_id
}

# --- Secrets ----------------------------------------------------------------

resource "aws_secretsmanager_secret" "pii_keyring" {
  name                    = "${var.name}/pii-keyring"
  description             = "PII master keyring for the Wenrix relay. Never regenerate while tokens are outstanding."
  recovery_window_in_days = 30
  kms_key_id              = local.kms_key_arn
}

resource "aws_secretsmanager_secret_version" "pii_keyring" {
  secret_id     = aws_secretsmanager_secret.pii_keyring.id
  secret_string = var.pii_keyring_json != "" ? var.pii_keyring_json : "{}"
}

# T1: basic-auth credentials, only created when basic auth is enabled.
resource "aws_secretsmanager_secret" "basic_auth" {
  count                   = var.basic_auth_enabled ? 1 : 0
  name                    = "${var.name}/basic-auth"
  description             = "Relay basic-auth credentials. Never regenerate while clients depend on the current password."
  recovery_window_in_days = 30
  kms_key_id              = local.kms_key_arn
}

resource "aws_secretsmanager_secret_version" "basic_auth" {
  count     = var.basic_auth_enabled ? 1 : 0
  secret_id = aws_secretsmanager_secret.basic_auth[0].id
  secret_string = jsonencode({
    user = var.basic_auth_user
    pass = var.basic_auth_pass
  })
}

# --- Logging ----------------------------------------------------------------

resource "aws_cloudwatch_log_group" "this" {
  name              = local.log_group_name
  retention_in_days = var.log_retention_days
  kms_key_id        = local.kms_key_arn
}

# --- IAM --------------------------------------------------------------------

data "aws_iam_policy_document" "assume_ecs" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.assume_ecs.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Scope the execution role to read ONLY this relay's secrets (PII keyring, optional
# basic-auth credentials, optional private-registry pull credentials).
data "aws_iam_policy_document" "secret_read" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = concat(
      [aws_secretsmanager_secret.pii_keyring.arn],
      var.basic_auth_enabled ? [aws_secretsmanager_secret.basic_auth[0].arn] : [],
      var.ghcr_credentials_secret_arn != "" ? [var.ghcr_credentials_secret_arn] : [],
    )
  }

  # Secrets encrypted with a CMK are unreadable without decrypt permission on the key
  # itself. Omitted when the AWS-managed key is in use, which needs no explicit grant.
  dynamic "statement" {
    for_each = local.kms_key_arn == null ? [] : [local.kms_key_arn]

    content {
      actions   = ["kms:Decrypt"]
      resources = [statement.value]

      condition {
        test     = "StringEquals"
        variable = "kms:ViaService"
        values   = ["secretsmanager.${var.region}.amazonaws.com"]
      }
    }
  }
}

resource "aws_iam_role_policy" "execution_secret" {
  name   = "${var.name}-secret-read"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.secret_read.json
}

# Intentionally has no attached policies: the relay makes no AWS API calls at runtime
# (config and secrets are injected by the execution role at task startup, not fetched by
# the app itself). Keep this role as the task role purely for least-privilege posture.
resource "aws_iam_role" "task" {
  name               = "${var.name}-task"
  assume_role_policy = data.aws_iam_policy_document.assume_ecs.json
}

# --- ECS --------------------------------------------------------------------

resource "aws_ecs_cluster" "this" {
  name = var.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "this" {
  family                   = var.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  # Writable /tmp for the read-only root filesystem.
  volume {
    name = "tmp"
  }

  container_definitions = jsonencode([
    merge(
      {
        name                   = "relay"
        image                  = local.image_tag
        essential              = true
        user                   = "100"
        readonlyRootFilesystem = true
        # T4: give the app time to drain in-flight requests on SIGTERM before SIGKILL.
        stopTimeout = 120
        # Write the (non-secret) channel config to a writable path, then exec the relay.
        entryPoint = ["/bin/sh", "-c"]
        command = [
          "printf '%s' \"$RELAY_CONFIG_JSON\" > /tmp/relay.json && exec channel-relay"
        ]
        portMappings = [
          { containerPort = var.container_port, protocol = "tcp" }
        ]
        environment = local.container_environment
        secrets     = local.container_secrets
        mountPoints = [
          { sourceVolume = "tmp", containerPath = "/tmp", readOnly = false }
        ]
        logConfiguration = {
          logDriver = "awslogs"
          options = {
            "awslogs-group"         = aws_cloudwatch_log_group.this.name
            "awslogs-region"        = var.region
            "awslogs-stream-prefix" = "relay"
          }
        }
      },
      # T7: pull the image with registry credentials only when configured.
      var.ghcr_credentials_secret_arn != "" ? {
        repositoryCredentials = { credentialsParameter = var.ghcr_credentials_secret_arn }
      } : {}
    )
  ])
}

resource "aws_ecs_service" "this" {
  name            = var.name
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  # Spread tasks across AZs for HA.
  availability_zone_rebalancing = "ENABLED"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.task.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.this.arn
    container_name   = "relay"
    container_port   = var.container_port
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  # T3: automatically roll back a bad deployment instead of leaving the service degraded.
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # T5: give the app time to pass its first health check before the deployment considers it unhealthy.
  health_check_grace_period_seconds = 60

  depends_on = [aws_lb_listener.https]
}

# --- Autoscaling ------------------------------------------------------------

resource "aws_appautoscaling_target" "this" {
  max_capacity       = var.max_capacity
  min_capacity       = var.min_capacity
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.this.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "cpu" {
  name               = "${var.name}-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.this.resource_id
  scalable_dimension = aws_appautoscaling_target.this.scalable_dimension
  service_namespace  = aws_appautoscaling_target.this.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value = var.cpu_target_utilization
  }
}

resource "aws_appautoscaling_policy" "alb_requests" {
  name               = "${var.name}-alb-requests"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.this.resource_id
  scalable_dimension = aws_appautoscaling_target.this.scalable_dimension
  service_namespace  = aws_appautoscaling_target.this.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"
      resource_label         = "${aws_lb.this.arn_suffix}/${aws_lb_target_group.this.arn_suffix}"
    }
    # ~50 rps/instance target.
    target_value = 50 * 60
  }
}

# --- Alarms -------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "${var.name}-alb-5xx"
  alarm_description   = "ALB returned >= 10 5XX responses in a 5 minute window."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_ELB_5XX_Count"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 10
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = aws_lb.this.arn_suffix
  }

  alarm_actions = var.alarm_sns_topic_arn != "" ? [var.alarm_sns_topic_arn] : []
  ok_actions    = var.alarm_sns_topic_arn != "" ? [var.alarm_sns_topic_arn] : []
}

resource "aws_cloudwatch_metric_alarm" "unhealthy_hosts" {
  alarm_name          = "${var.name}-unhealthy-hosts"
  alarm_description   = "At least one target behind the relay target group is unhealthy."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = aws_lb.this.arn_suffix
    TargetGroup  = aws_lb_target_group.this.arn_suffix
  }

  alarm_actions = var.alarm_sns_topic_arn != "" ? [var.alarm_sns_topic_arn] : []
  ok_actions    = var.alarm_sns_topic_arn != "" ? [var.alarm_sns_topic_arn] : []
}
