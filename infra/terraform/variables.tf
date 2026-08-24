variable "aws_region" {
  description = "AWS region for the myAQI deployment and Route 53 health metrics."
  type        = string
  default     = "us-east-1"

  validation {
    condition     = var.aws_region == "us-east-1"
    error_message = "This root currently requires us-east-1 for Route 53 health alarms."
  }
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

variable "device_master_secret_arn" {
  description = "ARN of a Secrets Manager secret containing the device master key."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:secretsmanager:", var.device_master_secret_arn))
    error_message = "device_master_secret_arn must be an AWS Secrets Manager ARN."
  }
}

variable "initial_image_tag" {
  description = "Existing immutable ECR image tag used to bootstrap ECS services."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_][A-Za-z0-9_.-]{6,127}$", var.initial_image_tag))
    error_message = "initial_image_tag must be an ECR-compatible immutable tag."
  }
}

variable "service_version" {
  description = "Human-readable application version exposed by health checks."
  type        = string
  default     = "0.1.0"
}

variable "api_desired_count" {
  description = "Number of API tasks."
  type        = number
  default     = 2
}

variable "worker_desired_count" {
  description = "Number of outbox worker tasks."
  type        = number
  default     = 1
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention."
  type        = number
  default     = 30
}

variable "alarm_email" {
  description = "Optional email endpoint for operational alarms; subscription requires confirmation."
  type        = string
  default     = null

  validation {
    condition     = var.alarm_email == null || can(regex("^[^@]+@[^@]+\\.[^@]+$", var.alarm_email))
    error_message = "alarm_email must be null or a valid email address."
  }
}

variable "github_repository" {
  description = "GitHub owner/repository allowed to deploy."
  type        = string
  default     = "rdfds/myaqi-iot-platform"
}

variable "github_environment" {
  description = "Protected GitHub environment allowed to assume the deployment role."
  type        = string
  default     = "aws-staging"
}

variable "github_oidc_provider_arn" {
  description = "Existing GitHub Actions OIDC provider ARN; null creates one in this account."
  type        = string
  default     = null
}

variable "github_oidc_thumbprints" {
  description = "Fallback CA thumbprints for the GitHub Actions OIDC provider."
  type        = list(string)
  default = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1b511abead59c6ce207077c0bf0e0043b1382612",
  ]
}
