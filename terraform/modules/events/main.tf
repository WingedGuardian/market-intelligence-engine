variable "environment" { type = string }

# SQS FIFO queue--collectors drop messages, extractor processes them
# FIFO because duplicate articles from overlapping RSS feeds shouldn't
# get extracted twice. content-based dedup handles this for free.
resource "aws_sqs_queue" "signals" {
  name                        = "intent-signals-${var.environment}.fifo"
  fifo_queue                  = true
  content_based_deduplication = true

  visibility_timeout_seconds = 300   # extractor needs time for bedrock calls
  message_retention_seconds  = 86400 # 1 day--signals older than that are stale

  # DLQ for messages that fail extraction 3 times
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sqs_queue" "dlq" {
  name                      = "intent-signals-dlq-${var.environment}.fifo"
  fifo_queue                = true
  message_retention_seconds = 604800 # 7 days for debugging
}

# SNS topic for hot lead alerts--subscribers get email/slack/webhook
resource "aws_sns_topic" "alerts" {
  name = "intent-hot-leads-${var.environment}"
}

# EventBridge rule--triggers collectors every 15 minutes
resource "aws_cloudwatch_event_rule" "collector_schedule" {
  name                = "intent-collector-${var.environment}"
  schedule_expression = "rate(15 minutes)"
  state               = var.environment == "demo" ? "DISABLED" : "ENABLED"
}

output "sqs_queue_arn" { value = aws_sqs_queue.signals.arn }
output "sqs_queue_url" { value = aws_sqs_queue.signals.url }
output "sns_topic_arn" { value = aws_sns_topic.alerts.arn }
output "schedule_rule_name" { value = aws_cloudwatch_event_rule.collector_schedule.name }
