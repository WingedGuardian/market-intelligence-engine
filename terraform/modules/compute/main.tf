variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "public_subnet_ids" { type = list(string) }
variable "schedule_rule_name" { type = string }
variable "database_url" {
  type      = string
  sensitive = true
}
variable "sqs_queue_arn" { type = string }
variable "sqs_queue_url" { type = string }
variable "sns_topic_arn" { type = string }
variable "bedrock_model_id" { type = string }
variable "container_image" {
  type    = string
  default = "python:3.12-slim"
}

# --- IAM ---

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "intent-lambda-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# least privilege: only the specific queue, topic, and bedrock model
data "aws_iam_policy_document" "lambda_permissions" {
  statement {
    sid = "SQSAccess"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:SendMessage",
    ]
    resources = [var.sqs_queue_arn]
  }

  statement {
    sid       = "SNSPublish"
    actions   = ["sns:Publish"]
    resources = [var.sns_topic_arn]
  }

  statement {
    sid       = "BedrockInvoke"
    actions   = ["bedrock:InvokeModel"]
    resources = ["arn:aws:bedrock:*::foundation-model/${var.bedrock_model_id}"]
  }

  statement {
    sid = "Logs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }

  # VPC execution (ENI management)
  statement {
    sid = "VPCAccess"
    actions = [
      "ec2:CreateNetworkInterface",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DeleteNetworkInterface",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "intent-lambda-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

# --- Dedicated Fargate IAM role (execution + task) ---

data "aws_iam_policy_document" "fargate_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "fargate_execution" {
  name               = "intent-fargate-execution-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.fargate_assume.json
}

data "aws_iam_policy_document" "fargate_execution_permissions" {
  statement {
    sid = "ECRAuth"
    actions = [
      "ecr:GetAuthorizationToken",
    ]
    resources = ["*"]
  }

  statement {
    sid = "ECRPull"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
    ]
    resources = ["arn:aws:ecr:*:*:repository/intent-engine"]
  }

  statement {
    sid = "Logs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }

  statement {
    sid = "SecretsManagerRead"
    actions = [
      "secretsmanager:GetSecretValue",
    ]
    resources = ["arn:aws:secretsmanager:*:*:secret:intent-engine/${var.environment}/*"]
  }
}

resource "aws_iam_role_policy" "fargate_execution" {
  name   = "intent-fargate-execution-policy"
  role   = aws_iam_role.fargate_execution.id
  policy = data.aws_iam_policy_document.fargate_execution_permissions.json
}

resource "aws_iam_role" "fargate_task" {
  name               = "intent-fargate-task-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.fargate_assume.json
}

data "aws_iam_policy_document" "fargate_task_permissions" {
  statement {
    sid       = "BedrockInvoke"
    actions   = ["bedrock:InvokeModel"]
    resources = ["arn:aws:bedrock:*::foundation-model/${var.bedrock_model_id}"]
  }

  statement {
    sid = "Logs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }
}

resource "aws_iam_role_policy" "fargate_task" {
  name   = "intent-fargate-task-policy"
  role   = aws_iam_role.fargate_task.id
  policy = data.aws_iam_policy_document.fargate_task_permissions.json
}

# --- Security Groups ---

resource "aws_security_group" "lambda" {
  name_prefix = "intent-lambda-"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "lambda needs outbound for bedrock, sqs, rds"
  }
}

resource "aws_security_group" "fargate" {
  name_prefix = "intent-api-"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "api traffic"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --- Lambda Functions ---

# placeholder zip--real deployment uses CI/CD to build and upload
data "archive_file" "lambda_placeholder" {
  type        = "zip"
  output_path = "${path.module}/placeholder.zip"

  source {
    content  = "def handler(event, context): pass"
    filename = "handler.py"
  }
}

resource "aws_lambda_function" "rss_collector" {
  function_name = "intent-rss-collector-${var.environment}"
  role          = aws_iam_role.lambda.arn
  handler       = "src.collectors.rss.handler"
  runtime       = "python3.12"
  timeout       = 60
  memory_size   = 256

  filename         = data.archive_file.lambda_placeholder.output_path
  source_code_hash = data.archive_file.lambda_placeholder.output_base64sha256

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      SQS_QUEUE_URL = var.sqs_queue_url
    }
  }
}

resource "aws_lambda_function" "edgar_collector" {
  function_name = "intent-edgar-collector-${var.environment}"
  role          = aws_iam_role.lambda.arn
  handler       = "src.collectors.edgar.handler"
  runtime       = "python3.12"
  timeout       = 60
  memory_size   = 256

  filename         = data.archive_file.lambda_placeholder.output_path
  source_code_hash = data.archive_file.lambda_placeholder.output_base64sha256

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      SQS_QUEUE_URL = var.sqs_queue_url
    }
  }
}

resource "aws_lambda_function" "extractor" {
  function_name = "intent-extractor-${var.environment}"
  role          = aws_iam_role.lambda.arn
  handler       = "src.extractor.handler.handler"
  runtime       = "python3.12"
  timeout       = 300 # bedrock calls can be slow
  memory_size   = 512

  filename         = data.archive_file.lambda_placeholder.output_path
  source_code_hash = data.archive_file.lambda_placeholder.output_base64sha256

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      DATABASE_URL     = var.database_url
      SQS_QUEUE_URL    = var.sqs_queue_url
      BEDROCK_MODEL_ID = var.bedrock_model_id
    }
  }
}

resource "aws_lambda_function" "scorer" {
  function_name = "intent-scorer-${var.environment}"
  role          = aws_iam_role.lambda.arn
  handler       = "src.scorer.handler.handler"
  runtime       = "python3.12"
  timeout       = 120
  memory_size   = 256

  filename         = data.archive_file.lambda_placeholder.output_path
  source_code_hash = data.archive_file.lambda_placeholder.output_base64sha256

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      DATABASE_URL  = var.database_url
      SNS_TOPIC_ARN = var.sns_topic_arn
    }
  }
}

# SQS → extractor trigger
resource "aws_lambda_event_source_mapping" "sqs_extractor" {
  event_source_arn = var.sqs_queue_arn
  function_name    = aws_lambda_function.extractor.arn
  batch_size       = 5 # process 5 articles per invocation
}

# --- Fargate (API) ---

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/intent-api-${var.environment}"
  retention_in_days = 30
}

resource "aws_ecs_cluster" "main" {
  name = "intent-engine-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "intent-api-${var.environment}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.fargate_execution.arn
  task_role_arn            = aws_iam_role.fargate_task.arn

  container_definitions = jsonencode([{
    name  = "api"
    image = var.container_image
    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]
    environment = [
      { name = "DATABASE_URL", value = var.database_url },
      { name = "AWS_REGION", value = "us-east-1" },
      { name = "BEDROCK_MODEL_ID", value = var.bedrock_model_id },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/ecs/intent-api-${var.environment}"
        "awslogs-region"        = "us-east-1"
        "awslogs-stream-prefix" = "api"
      }
    }
  }])
}

resource "aws_ecs_service" "api" {
  name            = "intent-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1 # single instance for demo--scale with load in prod
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [aws_security_group.fargate.id]
    assign_public_ip = true # demo shortcut--ALB in production
  }
}

# --- EventBridge Targets (here because we need the Lambda ARNs) ---

resource "aws_cloudwatch_event_target" "rss" {
  rule = var.schedule_rule_name
  arn  = aws_lambda_function.rss_collector.arn
}

resource "aws_cloudwatch_event_target" "edgar" {
  rule = var.schedule_rule_name
  arn  = aws_lambda_function.edgar_collector.arn
}

resource "aws_lambda_permission" "eventbridge_rss" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.rss_collector.function_name
  principal     = "events.amazonaws.com"
}

resource "aws_lambda_permission" "eventbridge_edgar" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.edgar_collector.function_name
  principal     = "events.amazonaws.com"
}

output "api_url" {
  value = "http://<fargate-public-ip>:8000" # in production, this comes from an ALB
}
