# Placeholder backend configuration.
#
# This block is intentionally commented out. It documents the convention that will be populated
# once Task 2.1 (Terraform module for the S3-native remote state backend) creates the actual
# KMS-encrypted, versioned S3 bucket. Do NOT hardcode a real bucket/key/region here until that
# bucket exists — an uncommented `backend "s3"` block pointing at a nonexistent bucket will break
# `terraform init` for every contributor.
#
# Convention (one backend config per environment/target, per infra/README.md and design.md
# Component 4 / Dependencies):
#   - bucket         = "<state-bucket-name-from-task-2.1>"
#   - key            = "daf-phase1/<environment>/terraform.tfstate"
#   - region         = var.aws_region equivalent, hardcoded here since backend blocks can't
#                       reference variables
#   - encrypt        = true
#   - use_lockfile   = true   # S3-native locking, no DynamoDB lock table (Terraform >= 1.11)
#
terraform {
  backend "s3" {
    bucket       = "daf-tfstate-dev-669076482267"
    key          = "daf-phase1/dev/terraform.tfstate"
    region       = "ap-southeast-2"
    kms_key_id   = "arn:aws:kms:ap-southeast-2:669076482267:key/3007fc05-ec31-42ff-bce6-44891023b841"
    encrypt      = true
    use_lockfile = true
  }
}
