terraform {
  # Matches the root module's floor (see ../../versions.tf) so this module can be consumed
  # standalone (e.g. bootstrapped before the root module's own backend block can be configured).
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
