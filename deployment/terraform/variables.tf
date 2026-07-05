variable "region" {
  description = "AWS region."
  type        = string
}

variable "name" {
  description = "Name prefix for all resources."
  type        = string
  default     = "wenrix-relay"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones (>= 2 for HA)."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 2
    error_message = "az_count must be at least 2 for high availability."
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
  description = "Fargate task CPU units (1024 = 1 vCPU). Baseline is 1 vCPU (PROJECT.md §13.4)."
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
  default     = "{\"channels\":[]}"
}

variable "pii_keyring_json" {
  description = "PII keyring JSON {\"<epoch>\":\"<base64(32B)>\"}. Stored in Secrets Manager."
  type        = string
  sensitive   = true
  default     = ""
}

variable "pii_key_epoch_active" {
  description = "Active PII key epoch."
  type        = number
  default     = 0
}

variable "otlp_endpoint" {
  description = "OTLP telemetry endpoint (host:port). Empty disables explicit override."
  type        = string
  default     = ""
}

variable "basic_auth_enabled" {
  description = "Enable relay basic auth."
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days."
  type        = number
  default     = 30
}
