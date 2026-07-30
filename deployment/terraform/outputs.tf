output "alb_dns_name" {
  description = "Public DNS name of the relay load balancer."
  value       = aws_lb.this.dns_name
}

output "cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.this.name
}

output "service_name" {
  description = "ECS service name."
  value       = aws_ecs_service.this.name
}

output "log_group" {
  description = "CloudWatch log group for relay tasks."
  value       = aws_cloudwatch_log_group.this.name
}

output "kms_key_arn" {
  description = "KMS key encrypting the relay's secrets and log group. Null when the AWS-managed keys are in use."
  value       = local.kms_key_arn
}

output "pii_keyring_secret_arn" {
  description = "Secrets Manager ARN holding the PII keyring."
  value       = aws_secretsmanager_secret.pii_keyring.arn
}
