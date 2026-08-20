output "oidc_provider_arn" {
  description = "ARN of the GitHub Actions OIDC identity provider (created by this module, or the existing provider passed in via var.oidc_provider_arn)."
  value       = local.oidc_provider_arn
}

output "role_arn" {
  description = <<-EOT
    ARN of the IAM role assumed by GitHub Actions via OIDC. Reference this in the workflow's
    `role-to-assume` input for `aws-actions/configure-aws-credentials` (see README for an example).
  EOT
  value       = aws_iam_role.github_actions.arn
}

output "role_name" {
  description = "Name of the IAM role assumed by GitHub Actions via OIDC."
  value       = aws_iam_role.github_actions.name
}
