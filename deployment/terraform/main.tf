locals {
  image_tag = var.image
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

  egress {
    description = "To relay tasks"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.name}-alb" }
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

resource "aws_lb" "this" {
  name               = var.name
  load_balancer_type = "application"
  internal           = false
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids

  drop_invalid_header_fields = true
  enable_deletion_protection = false
}

resource "aws_lb_target_group" "this" {
  name        = var.name
  port        = var.container_port
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

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

# --- Secrets ----------------------------------------------------------------

resource "aws_secretsmanager_secret" "pii_keyring" {
  name                    = "${var.name}/pii-keyring"
  description             = "PII master keyring for the Wenrix relay. Never regenerate while tokens are outstanding."
  recovery_window_in_days = 30
}

resource "aws_secretsmanager_secret_version" "pii_keyring" {
  secret_id     = aws_secretsmanager_secret.pii_keyring.id
  secret_string = var.pii_keyring_json != "" ? var.pii_keyring_json : "{}"
}

# --- Logging ----------------------------------------------------------------

resource "aws_cloudwatch_log_group" "this" {
  name              = "/ecs/${var.name}"
  retention_in_days = var.log_retention_days
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

# Scope the execution role to read ONLY this relay's secret.
data "aws_iam_policy_document" "secret_read" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.pii_keyring.arn]
  }
}

resource "aws_iam_role_policy" "execution_secret" {
  name   = "${var.name}-secret-read"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.secret_read.json
}

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
    {
      name                   = "relay"
      image                  = local.image_tag
      essential              = true
      user                   = "100"
      readonlyRootFilesystem = true
      # Write the (non-secret) channel config to a writable path, then exec the relay.
      entryPoint = ["/bin/sh", "-c"]
      command = [
        "printf '%s' \"$RELAY_CONFIG_JSON\" > /tmp/relay.json && exec channel-relay"
      ]
      portMappings = [
        { containerPort = var.container_port, protocol = "tcp" }
      ]
      environment = [
        { name = "RELAY_CONFIG_FILE", value = "/tmp/relay.json" },
        { name = "RELAY_CONFIG_JSON", value = var.relay_config_json },
        { name = "RELAY_PORT", value = tostring(var.container_port) },
        { name = "RELAY_PII_KEY_EPOCH_ACTIVE", value = tostring(var.pii_key_epoch_active) },
        { name = "RELAY_BASIC_AUTH_ENABLED", value = tostring(var.basic_auth_enabled) },
        { name = "RELAY_OTLP_ENDPOINT", value = var.otlp_endpoint },
      ]
      secrets = [
        { name = "RELAY_PII_KEYRING", valueFrom = aws_secretsmanager_secret.pii_keyring.arn }
      ]
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
    }
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
