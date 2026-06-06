variable "aws_region" {
  default = "us-east-1"
}

variable "environment" {
  default = "demo"
}

variable "vpc_cidr" {
  default = "10.0.0.0/16"
}

variable "db_instance_class" {
  # smallest available--this is a demo, not a data warehouse
  default = "db.t4g.micro"
}

variable "bedrock_model_id" {
  default = "anthropic.claude-3-haiku-20240307-v1:0"
}

variable "container_image" {
  description = "ECR image URI for the FastAPI container"
  default     = "python:3.12-slim"
}
