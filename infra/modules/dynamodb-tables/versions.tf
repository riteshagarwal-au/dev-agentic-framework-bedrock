terraform {
  # Matches the root module's floor (see ../../versions.tf) so this module can be validated
  # standalone.
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
