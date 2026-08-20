# One-time bootstrap: applies the state-backend module with LOCAL state
# (chicken-and-egg — this bucket can't hold its own state before it exists).
# After apply, infra/backend.tf is configured to point at this bucket for
# all subsequent root-module state.

terraform {
  required_version = ">= 1.11"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "ap-southeast-2"
}

variable "environment" {
  type    = string
  default = "dev"
}

module "state_backend" {
  source      = "../modules/state-backend"
  environment = var.environment
  tags = {
    Project = "daf-phase1"
  }
}

output "bucket_name" {
  value = module.state_backend.bucket_name
}

output "kms_key_arn" {
  value = module.state_backend.kms_key_arn
}

output "backend_config_example" {
  value = module.state_backend.backend_config_example
}
