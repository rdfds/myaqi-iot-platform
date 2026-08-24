resource "aws_ecs_cluster" "main" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "enhanced"
  }

  configuration {
    execute_command_configuration {
      logging = "DEFAULT"
    }
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.name}/api"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${local.name}/worker"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "migration" {
  name              = "/ecs/${local.name}/migration"
  retention_in_days = var.log_retention_days
}

resource "aws_sns_topic" "outbox" {
  name              = "${local.name}-events"
  kms_master_key_id = "alias/aws/sns"
}

locals {
  image = "${aws_ecr_repository.backend.repository_url}:${var.initial_image_tag}"
  database_environment = [
    { name = "DB_HOST", value = aws_db_instance.main.address },
    { name = "DB_PORT", value = tostring(aws_db_instance.main.port) },
    { name = "DB_NAME", value = var.database_name },
  ]
  database_secrets = [
    {
      name      = "DB_USER"
      valueFrom = "${aws_db_instance.main.master_user_secret[0].secret_arn}:username::"
    },
    {
      name      = "DB_PASSWORD"
      valueFrom = "${aws_db_instance.main.master_user_secret[0].secret_arn}:password::"
    },
  ]
  common_environment = [
    { name = "APP_ENVIRONMENT", value = var.environment },
    { name = "APP_REVISION", value = var.initial_image_tag },
    { name = "SERVICE_VERSION", value = var.service_version },
    { name = "LOG_LEVEL", value = "INFO" },
  ]
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.api_task.arn

  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name                   = "api"
      image                  = local.image
      essential              = true
      readonlyRootFilesystem = true
      linuxParameters        = { initProcessEnabled = true }
      portMappings = [
        {
          name          = "http"
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
          appProtocol   = "http"
        }
      ]
      environment = concat(local.database_environment, local.common_environment)
      secrets = concat(local.database_secrets, [
        {
          name      = "DEVICE_MASTER_KEY"
          valueFrom = var.device_master_secret_arn
        }
      ])
      healthCheck = {
        command = [
          "CMD-SHELL",
          "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready')\"",
        ]
        interval    = 15
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.api.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "api"
        }
      }
    }
  ])
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.worker_task.arn

  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name                   = "worker"
      image                  = local.image
      essential              = true
      command                = ["myaqi-worker"]
      readonlyRootFilesystem = true
      stopTimeout            = 120
      linuxParameters        = { initProcessEnabled = true }
      environment = concat(local.database_environment, local.common_environment, [
        { name = "OUTBOX_SNS_TOPIC_ARN", value = aws_sns_topic.outbox.arn },
        { name = "OUTBOX_HEALTH_INTERVAL_SECONDS", value = "60" },
      ])
      secrets = local.database_secrets
      healthCheck = {
        command     = ["CMD-SHELL", "kill -0 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 10
      }
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.worker.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "worker"
        }
      }
    }
  ])
}

resource "aws_ecs_task_definition" "migration" {
  family                   = "${local.name}-migration"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.worker_task.arn

  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([
    {
      name                   = "migration"
      image                  = local.image
      essential              = true
      command                = ["alembic", "upgrade", "head"]
      readonlyRootFilesystem = true
      environment            = concat(local.database_environment, local.common_environment)
      secrets                = local.database_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.migration.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "migration"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "api" {
  name                   = "${local.name}-api"
  cluster                = aws_ecs_cluster.main.id
  task_definition        = aws_ecs_task_definition.api.arn
  desired_count          = var.api_desired_count
  enable_execute_command = true
  propagate_tags         = "SERVICE"

  health_check_grace_period_seconds = 60

  deployment_configuration {
    strategy             = "CANARY"
    bake_time_in_minutes = 5

    canary_configuration {
      canary_percent              = 10
      canary_bake_time_in_minutes = 5
    }
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  alarms {
    enable   = true
    rollback = true
    alarm_names = [
      aws_cloudwatch_metric_alarm.application_5xx.alarm_name,
      aws_cloudwatch_metric_alarm.unhealthy_targets_primary.alarm_name,
      aws_cloudwatch_metric_alarm.unhealthy_targets_alternate.alarm_name,
    ]
  }

  network_configuration {
    assign_public_ip = false
    subnets          = aws_subnet.application[*].id
    security_groups  = [aws_security_group.api.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000

    advanced_configuration {
      alternate_target_group_arn = aws_lb_target_group.api_alternate.arn
      production_listener_rule   = aws_lb_listener_rule.api.arn
      role_arn                   = aws_iam_role.ecs_load_balancer.arn
    }
  }

  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [
    aws_lb_listener.https,
    aws_iam_role_policy.ecs_secrets,
    aws_iam_role_policy_attachment.ecs_load_balancer,
  ]
}

resource "aws_ecs_service" "worker" {
  name                   = "${local.name}-worker"
  cluster                = aws_ecs_cluster.main.id
  task_definition        = aws_ecs_task_definition.worker.arn
  desired_count          = var.worker_desired_count
  enable_execute_command = true
  propagate_tags         = "SERVICE"

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    assign_public_ip = false
    subnets          = aws_subnet.application[*].id
    security_groups  = [aws_security_group.worker.id]
  }

  lifecycle {
    ignore_changes = [task_definition]
  }

  depends_on = [aws_iam_role_policy.ecs_secrets]
}
