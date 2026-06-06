terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # remote state for team environments--local for demos
  # backend "s3" {
  #   bucket = "intent-engine-tfstate"
  #   key    = "prod/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "intent-engine"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

module "networking" {
  source = "./modules/networking"

  environment = var.environment
  vpc_cidr    = var.vpc_cidr
}

module "data" {
  source = "./modules/data"

  environment       = var.environment
  vpc_id            = module.networking.vpc_id
  private_subnet_ids = module.networking.private_subnet_ids
  db_instance_class = var.db_instance_class
}

module "events" {
  source = "./modules/events"

  environment = var.environment
}

module "compute" {
  source = "./modules/compute"

  environment        = var.environment
  vpc_id             = module.networking.vpc_id
  private_subnet_ids = module.networking.private_subnet_ids
  public_subnet_ids  = module.networking.public_subnet_ids

  database_url       = module.data.database_url
  sqs_queue_arn      = module.events.sqs_queue_arn
  sqs_queue_url      = module.events.sqs_queue_url
  sns_topic_arn      = module.events.sns_topic_arn
  schedule_rule_name = module.events.schedule_rule_name
  bedrock_model_id   = var.bedrock_model_id
}
