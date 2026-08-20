output "bucket_name" {
  description = "Name of the S3 bucket holding Terraform state for this environment/target."
  value       = aws_s3_bucket.state.id
}

output "bucket_arn" {
  description = "ARN of the S3 bucket holding Terraform state for this environment/target."
  value       = aws_s3_bucket.state.arn
}

output "kms_key_arn" {
  description = "ARN of the KMS key used to encrypt this state bucket (created by this module, or the existing key passed in via var.kms_key_arn)."
  value       = local.kms_key_arn
}

output "kms_key_id" {
  description = "Key ID of the KMS key created by this module, if create_kms_key = true. Null when reusing an existing key."
  value       = var.create_kms_key ? aws_kms_key.state[0].key_id : null
}

output "backend_config_example" {
  description = "Example `backend \"s3\" {}` configuration block for consumers of this state bucket. Interpolate the `key` per root module/workspace to avoid state-path collisions within the same bucket."
  value       = <<-EOT
    terraform {
      backend "s3" {
        bucket       = "${aws_s3_bucket.state.id}"
        key          = "<component>/${var.environment}/terraform.tfstate"
        region       = "<aws_region>"
        kms_key_id   = "${local.kms_key_arn}"
        encrypt      = true
        use_lockfile = true
      }
    }
  EOT
}
