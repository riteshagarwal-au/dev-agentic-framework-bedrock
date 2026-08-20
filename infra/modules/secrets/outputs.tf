output "github_token_secret_arn" {
  description = <<-EOT
    ARN of the DevOps agent's GitHub token secret (PR-open scope). Feeds Task 3.4's
    agent-iam-roles module `github_token_secret_arn` input.
  EOT
  value       = aws_secretsmanager_secret.github_token.arn
}

output "github_token_secret_name" {
  description = "Name of the DevOps agent's GitHub token secret."
  value       = aws_secretsmanager_secret.github_token.name
}

output "pr_reviewer_github_token_secret_arn" {
  description = <<-EOT
    ARN of the PR-Reviewer agent's read-only-scoped GitHub token secret — a distinct secret ARN
    from `github_token_secret_arn`. Feeds Task 3.4's agent-iam-roles module
    `pr_reviewer_github_token_secret_arn` input.
  EOT
  value       = aws_secretsmanager_secret.pr_reviewer_github_token.arn
}

output "pr_reviewer_github_token_secret_name" {
  description = "Name of the PR-Reviewer agent's read-only-scoped GitHub token secret."
  value       = aws_secretsmanager_secret.pr_reviewer_github_token.name
}

output "azure_service_principal_secret_arn" {
  description = <<-EOT
    ARN of the Azure service-principal secret (JSON: clientId, clientSecret, tenantId). Feeds
    Task 3.4's agent-iam-roles module `azure_sp_secret_arn` input.
  EOT
  value       = aws_secretsmanager_secret.azure_service_principal.arn
}

output "azure_service_principal_secret_name" {
  description = "Name of the Azure service-principal secret."
  value       = aws_secretsmanager_secret.azure_service_principal.name
}

output "registry_credentials_secret_arn" {
  description = <<-EOT
    ARN of the container-registry credentials secret (JSON: username, password). Not currently
    consumed by Task 3.4's agent-iam-roles module (no agent role needs direct registry access in
    Phase 1) — this ARN is instead a forward dependency for Task 14.5's GitHub Actions
    container-build/deploy workflow, which authenticates to the registry via this secret.
  EOT
  value       = aws_secretsmanager_secret.registry_credentials.arn
}

output "registry_credentials_secret_name" {
  description = "Name of the container-registry credentials secret."
  value       = aws_secretsmanager_secret.registry_credentials.name
}

output "secret_arns" {
  description = "Map of all 4 secret ARNs keyed by credential purpose, for convenient use in IAM policy resource lists or module wiring."
  value = {
    github_token             = aws_secretsmanager_secret.github_token.arn
    pr_reviewer_github_token = aws_secretsmanager_secret.pr_reviewer_github_token.arn
    azure_service_principal  = aws_secretsmanager_secret.azure_service_principal.arn
    registry_credentials     = aws_secretsmanager_secret.registry_credentials.arn
  }
}

output "secret_names" {
  description = "Map of all 4 secret names keyed by credential purpose, for convenient use as CredentialsClient (Task 4.1) secret_name_map config/env vars."
  value = {
    github_token             = aws_secretsmanager_secret.github_token.name
    pr_reviewer_github_token = aws_secretsmanager_secret.pr_reviewer_github_token.name
    azure_service_principal  = aws_secretsmanager_secret.azure_service_principal.name
    registry_credentials     = aws_secretsmanager_secret.registry_credentials.name
  }
}

output "kms_key_arn" {
  description = "ARN of the KMS key used to encrypt all 4 secrets (created by this module, or the existing key passed in via var.kms_key_arn)."
  value       = local.kms_key_arn
}

output "kms_key_id" {
  description = "Key ID of the KMS key created by this module, if create_kms_key = true. Null when reusing an existing key."
  value       = var.create_kms_key ? aws_kms_key.secrets[0].key_id : null
}

output "standalone_read_policy_arns" {
  description = <<-EOT
    Map of credential purpose -> standalone IAM policy ARN, only populated when
    var.create_standalone_read_policies = true (default false). Each policy grants
    secretsmanager:GetSecretValue on exactly one of the 4 secrets, for attachment to any
    consumer that is not one of Task 3.4's agent-iam-roles roles. Empty map when
    create_standalone_read_policies = false.
  EOT
  value = var.create_standalone_read_policies ? {
    github_token             = aws_iam_policy.read_github_token[0].arn
    pr_reviewer_github_token = aws_iam_policy.read_pr_reviewer_github_token[0].arn
    azure_service_principal  = aws_iam_policy.read_azure_service_principal[0].arn
    registry_credentials     = aws_iam_policy.read_registry_credentials[0].arn
  } : {}
}
