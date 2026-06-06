variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "db_instance_class" { type = string }

resource "aws_db_subnet_group" "main" {
  name       = "intent-engine-${var.environment}"
  subnet_ids = var.private_subnet_ids
}

resource "aws_security_group" "rds" {
  name_prefix = "intent-rds-"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]  # VPC-internal only
    description = "postgres from VPC"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "random_password" "db" {
  length  = 24
  special = false  # avoid shell escaping headaches in connection strings
}

resource "aws_secretsmanager_secret" "db_password" {
  name                    = "intent-engine/${var.environment}/db-password"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id     = aws_secretsmanager_secret.db_password.id
  secret_string = random_password.db.result
}

resource "aws_rds_cluster" "main" {
  cluster_identifier = "intent-engine-${var.environment}"
  engine             = "aurora-postgresql"
  engine_mode        = "provisioned"
  engine_version     = "16.1"
  database_name      = "intent_engine"
  master_username    = "intent"
  master_password    = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  storage_encrypted       = true
  backup_retention_period = 30

  # Aurora Serverless v2--scales to zero when idle
  serverlessv2_scaling_configuration {
    min_capacity = 0.5  # lowest possible--$0.12/hr when active
    max_capacity = 2.0
  }

  skip_final_snapshot = var.environment == "demo"
  # prevent_destroy = true  # enable after first successful deploy

  tags = { Name = "intent-engine-db" }
}

resource "aws_rds_cluster_instance" "main" {
  cluster_identifier = aws_rds_cluster.main.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.main.engine
  engine_version     = aws_rds_cluster.main.engine_version
}

output "database_endpoint" {
  value = aws_rds_cluster.main.endpoint
}

output "database_url" {
  value     = "postgresql://intent:${random_password.db.result}@${aws_rds_cluster.main.endpoint}:5432/intent_engine"
  sensitive = true
}

output "db_password_secret_arn" {
  description = "ARN of the Secrets Manager secret containing the DB password"
  value       = aws_secretsmanager_secret.db_password.arn
  sensitive   = false
}
