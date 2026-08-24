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
