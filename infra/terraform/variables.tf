variable "aws_region" {
  description = "AWS region for the myAQI deployment."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short project identifier used in resource names."
  type        = string
  default     = "myaqi"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.project_name))
    error_message = "project_name must be 2-21 lowercase letters, numbers, or hyphens."
  }
}

variable "environment" {
  description = "Deployment environment label."
  type        = string
  default     = "staging"

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production."
  }
}

variable "vpc_cidr" {
  description = "CIDR assigned to the deployment VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "database_name" {
  description = "Initial PostgreSQL database."
  type        = string
  default     = "myaqi"
}

variable "database_username" {
  description = "RDS master username; its password is generated and managed by RDS."
  type        = string
  default     = "myaqi_admin"
  sensitive   = true
}

variable "database_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "database_multi_az" {
  description = "Run RDS synchronously across two availability zones."
  type        = bool
  default     = false
}

variable "database_deletion_protection" {
  description = "Prevent accidental database deletion."
  type        = bool
  default     = true
}

variable "domain_name" {
  description = "Public API hostname, for example api.myaqi.example."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]+[a-z0-9]$", var.domain_name))
    error_message = "domain_name must be a valid lowercase DNS hostname."
  }
}

variable "route53_zone_id" {
  description = "Route 53 public hosted zone containing domain_name."
  type        = string
}
