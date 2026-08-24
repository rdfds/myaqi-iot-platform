resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = aws_subnet.database[*].id
  tags       = { Name = local.name }
}

resource "aws_db_instance" "main" {
  identifier = local.name

  engine         = "postgres"
  engine_version = "16"
  instance_class = var.database_instance_class

  db_name  = var.database_name
  username = var.database_username
  port     = 5432

  manage_master_user_password = true
  storage_encrypted           = true
  allocated_storage           = 20
  max_allocated_storage       = 100
  storage_type                = "gp3"

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.database.id]
  publicly_accessible    = false
  multi_az               = var.database_multi_az

  backup_retention_period    = 7
  backup_window              = "03:00-04:00"
  maintenance_window         = "sun:04:30-sun:05:30"
  auto_minor_version_upgrade = true
  copy_tags_to_snapshot      = true

  performance_insights_enabled          = true
  performance_insights_retention_period = 7
  enabled_cloudwatch_logs_exports       = ["postgresql", "upgrade"]

  deletion_protection = var.database_deletion_protection
  skip_final_snapshot = false
  final_snapshot_identifier = "${local.name}-final-${formatdate(
    "YYYYMMDDhhmmss",
    timestamp()
  )}"

  lifecycle {
    ignore_changes = [final_snapshot_identifier]
  }
}
