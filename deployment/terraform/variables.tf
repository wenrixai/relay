variable "region" {
  description = "AWS region."
  type        = string
}

variable "name" {
  description = "Name prefix for all resources."
  type        = string
  default     = "wenrix-relay"
}

variable "vpc_id" {
  description = "Existing VPC ID to deploy into."
  type        = string
}

variable "public_subnet_ids" {
  description = "Existing public subnet IDs for the ALB (>= 2 for HA)."
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_ids) >= 2
    error_message = "Provide at least 2 public subnets across AZs for high availability."
  }
}

variable "private_subnet_ids" {
  description = "Existing private subnet IDs for the ECS tasks (>= 2 for HA)."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "Provide at least 2 private subnets across AZs for high availability."
  }
}

variable "image" {
  description = "Fully qualified relay image reference (e.g. ghcr.io/wenrixai/wenrix-relay:v0.1.0)."
  type        = string
}

variable "container_port" {
  description = "Port the relay listens on inside the container."
  type        = number
  default     = 8080
}

variable "task_cpu" {
  description = "Fargate task CPU units (1024 = 1 vCPU). Baseline is 1 vCPU."
  type        = number
  default     = 1024
}

variable "task_memory" {
  description = "Fargate task memory (MiB)."
  type        = number
  default     = 2048
}

variable "desired_count" {
  description = "Baseline number of tasks (autoscaling overrides between min and max)."
  type        = number
  default     = 2
}

variable "min_capacity" {
  description = "Minimum tasks for autoscaling (>= 2 for HA)."
  type        = number
  default     = 2
}

variable "max_capacity" {
  description = "Maximum tasks for autoscaling."
  type        = number
  default     = 10
}

variable "cpu_target_utilization" {
  description = "Target average CPU utilization percent for autoscaling."
  type        = number
  default     = 70
}

variable "wenrix_ingress_cidrs" {
  description = "CIDRs allowed to reach the ALB on HTTPS (the Wenrix client source)."
  type        = list(string)

  validation {
    condition     = length(var.wenrix_ingress_cidrs) > 0
    error_message = "Provide at least one ingress CIDR; do not expose the relay to 0.0.0.0/0."
  }
}

variable "certificate_arn" {
  description = "ACM certificate ARN for the HTTPS listener."
  type        = string
}

variable "relay_config_json" {
  description = "Channel configuration JSON (no secrets), written to the config file at startup."
  type        = string
  sensitive   = true
  default     = "{\"channels\":[]}"
}

variable "pii_keyring_json" {
  description = "PII keyring: a single base64(32-byte) master key. Stored in Secrets Manager."
  type        = string
  sensitive   = true
  default     = ""
}

variable "otlp_endpoint" {
  description = "OTLP/gRPC telemetry endpoint. Use http:// for a plaintext collector. Empty disables export."
  type        = string
  default     = ""
}

variable "basic_auth_enabled" {
  description = "Enable relay basic auth."
  type        = bool
  default     = true
}

variable "basic_auth_user" {
  description = "Basic auth username. Required (non-empty) when basic_auth_enabled = true; stored in Secrets Manager, never in the config JSON."
  type        = string
  sensitive   = true
  default     = ""
}

variable "basic_auth_pass" {
  description = "Basic auth password. Required (non-empty) when basic_auth_enabled = true; stored in Secrets Manager, never in the config JSON."
  type        = string
  sensitive   = true
  default     = ""
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days."
  type        = number
  default     = 30
}

variable "ghcr_credentials_secret_arn" {
  description = "Optional Secrets Manager ARN of a secret holding {\"username\":...,\"password\":...} for pulling the relay image from a private registry (e.g. GHCR). When empty, no repositoryCredentials are set and the execution role is not granted read access to it."
  type        = string
  default     = ""
}

variable "alarm_sns_topic_arn" {
  description = "Optional SNS topic ARN to notify on the ALB 5XX and unhealthy-host alarms. When empty, alarms are created without any alarm/ok actions."
  type        = string
  default     = ""
}
