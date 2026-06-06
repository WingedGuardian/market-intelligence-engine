output "api_url" {
  description = "Public URL for the FastAPI service"
  value       = module.compute.api_url
}

output "database_endpoint" {
  value     = module.data.database_endpoint
  sensitive = true
}

output "sqs_queue_url" {
  value = module.events.sqs_queue_url
}

output "sns_topic_arn" {
  value = module.events.sns_topic_arn
}
