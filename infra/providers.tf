provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_tag
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
