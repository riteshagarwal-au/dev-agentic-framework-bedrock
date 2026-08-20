terraform {
  # S3-native state locking (`use_lockfile = true`, see backend.tf) requires Terraform >= 1.11.
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
