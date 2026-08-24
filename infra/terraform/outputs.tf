output "vpc_id" {
  description = "Deployment VPC."
  value       = aws_vpc.main.id
}

output "application_subnet_ids" {
  description = "Private subnets used by ECS tasks."
  value       = aws_subnet.application[*].id
}

output "database_endpoint" {
  description = "Private RDS endpoint."
  value       = aws_db_instance.main.address
}

output "database_master_secret_arn" {
  description = "RDS-managed master credential secret."
  value       = aws_db_instance.main.master_user_secret[0].secret_arn
  sensitive   = true
}

output "ecr_repository_url" {
  description = "Immutable backend image repository."
  value       = aws_ecr_repository.backend.repository_url
}

output "api_url" {
  description = "TLS-protected public API origin."
  value       = "https://${var.domain_name}"
}

output "ecs_cluster_name" {
  description = "ECS cluster used by deployment automation."
  value       = aws_ecs_cluster.main.name
}

output "api_service_name" {
  description = "API ECS service."
  value       = aws_ecs_service.api.name
}

output "worker_service_name" {
  description = "Worker ECS service."
  value       = aws_ecs_service.worker.name
}

output "api_task_family" {
  description = "API task-definition family."
  value       = aws_ecs_task_definition.api.family
}

output "worker_task_family" {
  description = "Worker task-definition family."
  value       = aws_ecs_task_definition.worker.family
}

output "migration_task_family" {
  description = "Migration task-definition family."
  value       = aws_ecs_task_definition.migration.family
}

output "worker_security_group_id" {
  description = "Security group used for migration and worker tasks."
  value       = aws_security_group.worker.id
}

output "outbox_topic_arn" {
  description = "SNS topic receiving published outbox events."
  value       = aws_sns_topic.outbox.arn
}

output "alarm_topic_arn" {
  description = "SNS topic for CloudWatch alarm notifications."
  value       = aws_sns_topic.alarms.arn
}

output "operations_dashboard" {
  description = "CloudWatch operations dashboard name."
  value       = aws_cloudwatch_dashboard.operations.dashboard_name
}
