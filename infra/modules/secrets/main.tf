# ---------------------------------------------------------------------------
# secrets
#
# Provisions the 4 Secrets Manager secrets Requirement 11.2 names explicitly, per
# design.md "Security Considerations":
#   "Secrets (GitHub token, Azure SP, registry creds) live only in Secrets Manager, injected at
#   tool-call time — never in prompts/context/memory/logs."
#
# Requirement 11.2: "ALL credentials (GitHub token, Azure service principal, registry
# credentials) SHALL be stored in AWS Secrets Manager and injected at tool-call time only."
#
# This module's job is to CREATE the secrets and output their ARNs — Task 3.4's
# agent-iam-roles module is the primary consumer, taking those ARNs as its
# azure_sp_secret_arn / github_token_secret_arn / pr_reviewer_github_token_secret_arn inputs and
# building its own scoped IAM read statements against them (see that module's README, "Secrets
# Manager access" section). See README.md "Secondary deliverable" for the optional standalone
# IAM policies this module can also produce for any OTHER consumer.
#
# The GitHub token and PR-Reviewer GitHub token are deliberately two SEPARATE secret resources
# (never one secret shared between DevOps and PR-Reviewer) — per agent-iam-roles' explicit
# requirement that github_token_secret_arn and pr_reviewer_github_token_secret_arn must be
# distinct ARNs, so PR-Reviewer's read-only role can never reach a merge/approve-capable
# credential even indirectly.
# ---------------------------------------------------------------------------

locals {
  kms_key_arn = var.create_kms_key ? aws_kms_key.secrets[0].arn : var.kms_key_arn

  github_token_secret_name             = coalesce(var.github_token_secret_name, "${var.name_prefix}-github-token-${var.environment}")
  pr_reviewer_github_token_secret_name = coalesce(var.pr_reviewer_github_token_secret_name, "${var.name_prefix}-pr-reviewer-github-token-${var.environment}")
  azure_service_principal_secret_name  = coalesce(var.azure_service_principal_secret_name, "${var.name_prefix}-azure-service-principal-${var.environment}")
  registry_credentials_secret_name     = coalesce(var.registry_credentials_secret_name, "${var.name_prefix}-registry-credentials-${var.environment}")

  tags = merge(var.tags, {
    Environment = var.environment
    Purpose     = "daf-agent-credentials"
  })
}

# ---------------------------------------------------------------------------
# KMS key for secret encryption (optional — a caller can instead pass an existing key via
# kms_key_arn / create_kms_key = false), mirroring the create-or-reuse pattern used by
# modules/state-backend and modules/dynamodb-tables.
# ---------------------------------------------------------------------------

resource "aws_kms_key" "secrets" {
  count = var.create_kms_key ? 1 : 0

  description             = "KMS key for DAF Phase 1 agent credential secrets (${var.environment})"
  deletion_window_in_days = var.kms_key_deletion_window_in_days
  enable_key_rotation     = true

  tags = merge(var.tags, {
    Name        = "${var.name_prefix}-secrets-${var.environment}-kms"
    Environment = var.environment
  })
}

resource "aws_kms_alias" "secrets" {
  count = var.create_kms_key ? 1 : 0

  name          = "alias/${var.name_prefix}-secrets-${var.environment}"
  target_key_id = aws_kms_key.secrets[0].key_id
}

# ---------------------------------------------------------------------------
# GitHub token (DevOps agent — PR-open scope). Plain-string secret value, consumed via
# CredentialsClient.get_secret / get_credential(CredentialName.GITHUB_TOKEN) (Task 4.1).
# ---------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "github_token" {
  name                    = local.github_token_secret_name
  description             = "DevOps agent's GitHub token (PR-open scope only). Requirement 11.2. Real value populated out-of-band, not by Terraform."
  kms_key_id              = local.kms_key_arn
  recovery_window_in_days = var.recovery_window_in_days

  tags = merge(local.tags, {
    Name       = local.github_token_secret_name
    Credential = "github-token-devops"
  })
}

resource "aws_secretsmanager_secret_version" "github_token" {
  secret_id     = aws_secretsmanager_secret.github_token.id
  secret_string = var.github_token_placeholder

  # This module only ever writes the placeholder value above. The real token is populated
  # out-of-band (manual `aws secretsmanager put-secret-value`, or a separate secure
  # rotation/CI process) after apply; ignore_changes prevents a later `terraform apply` of this
  # module from clobbering that out-of-band value back to the placeholder.
  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ---------------------------------------------------------------------------
# PR-Reviewer's GitHub token (read-only scope). A SEPARATE secret resource/ARN from the DevOps
# token above — see agent-iam-roles module README for why these must never be the same secret.
# ---------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "pr_reviewer_github_token" {
  name                    = local.pr_reviewer_github_token_secret_name
  description             = "PR-Reviewer agent's GitHub token (read-only scope only, distinct from the DevOps PR-open token). Requirement 11.2. Real value populated out-of-band, not by Terraform."
  kms_key_id              = local.kms_key_arn
  recovery_window_in_days = var.recovery_window_in_days

  tags = merge(local.tags, {
    Name       = local.pr_reviewer_github_token_secret_name
    Credential = "github-token-pr-reviewer-readonly"
  })
}

resource "aws_secretsmanager_secret_version" "pr_reviewer_github_token" {
  secret_id     = aws_secretsmanager_secret.pr_reviewer_github_token.id
  secret_string = var.pr_reviewer_github_token_placeholder

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ---------------------------------------------------------------------------
# Azure service principal (Discovery agent's Azure MCP connector). JSON-structured:
# clientId, clientSecret, tenantId — consumed via
# CredentialsClient.get_secret_fields / get_credential(CredentialName.AZURE_SERVICE_PRINCIPAL)
# (Task 4.1).
# ---------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "azure_service_principal" {
  name                    = local.azure_service_principal_secret_name
  description             = "Azure service-principal credentials (JSON: clientId, clientSecret, tenantId) for the Discovery agent's Azure MCP connector. Requirement 11.2. Real value populated out-of-band, not by Terraform."
  kms_key_id              = local.kms_key_arn
  recovery_window_in_days = var.recovery_window_in_days

  tags = merge(local.tags, {
    Name       = local.azure_service_principal_secret_name
    Credential = "azure-service-principal"
  })
}

resource "aws_secretsmanager_secret_version" "azure_service_principal" {
  secret_id     = aws_secretsmanager_secret.azure_service_principal.id
  secret_string = var.azure_service_principal_placeholder

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ---------------------------------------------------------------------------
# Registry credentials (container registry auth for the synthetic app's build/push/deploy
# workflow, Task 14.5). JSON-structured: username, password — consumed via
# CredentialsClient.get_secret_fields / get_credential(CredentialName.REGISTRY_CREDENTIALS)
# (Task 4.1).
# ---------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "registry_credentials" {
  name                    = local.registry_credentials_secret_name
  description             = "Container registry credentials (JSON: username, password) for the synthetic app's image build/push workflow. Requirement 11.2. Real value populated out-of-band, not by Terraform."
  kms_key_id              = local.kms_key_arn
  recovery_window_in_days = var.recovery_window_in_days

  tags = merge(local.tags, {
    Name       = local.registry_credentials_secret_name
    Credential = "registry-credentials"
  })
}

resource "aws_secretsmanager_secret_version" "registry_credentials" {
  secret_id     = aws_secretsmanager_secret.registry_credentials.id
  secret_string = var.registry_credentials_placeholder

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ---------------------------------------------------------------------------
# Standalone read-only IAM policies (secondary/optional deliverable — see README).
#
# Task 3.4's agent-iam-roles module already builds its own scoped read statements when given
# this module's secret ARNs, so these standalone policies are NOT required for that primary
# integration path. They exist only for any OTHER consumer (e.g. a CI/CD role) that needs
# secretsmanager:GetSecretValue on exactly one of these secrets and isn't one of the 7 agent
# roles. Gated behind create_standalone_read_policies (default false) since no such consumer
# exists yet in Phase 1.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "read_github_token" {
  count = var.create_standalone_read_policies ? 1 : 0

  statement {
    sid       = "ReadGitHubTokenSecret"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.github_token.arn]
  }
}

resource "aws_iam_policy" "read_github_token" {
  count = var.create_standalone_read_policies ? 1 : 0

  name        = "${var.name_prefix}-read-github-token-secret-${var.environment}"
  description = "Grants secretsmanager:GetSecretValue on exactly the DevOps GitHub token secret (${local.github_token_secret_name})."
  policy      = data.aws_iam_policy_document.read_github_token[0].json

  tags = local.tags
}

data "aws_iam_policy_document" "read_pr_reviewer_github_token" {
  count = var.create_standalone_read_policies ? 1 : 0

  statement {
    sid       = "ReadPrReviewerGitHubTokenSecret"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.pr_reviewer_github_token.arn]
  }
}

resource "aws_iam_policy" "read_pr_reviewer_github_token" {
  count = var.create_standalone_read_policies ? 1 : 0

  name        = "${var.name_prefix}-read-pr-reviewer-github-token-secret-${var.environment}"
  description = "Grants secretsmanager:GetSecretValue on exactly the PR-Reviewer read-only GitHub token secret (${local.pr_reviewer_github_token_secret_name})."
  policy      = data.aws_iam_policy_document.read_pr_reviewer_github_token[0].json

  tags = local.tags
}

data "aws_iam_policy_document" "read_azure_service_principal" {
  count = var.create_standalone_read_policies ? 1 : 0

  statement {
    sid       = "ReadAzureServicePrincipalSecret"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.azure_service_principal.arn]
  }
}

resource "aws_iam_policy" "read_azure_service_principal" {
  count = var.create_standalone_read_policies ? 1 : 0

  name        = "${var.name_prefix}-read-azure-sp-secret-${var.environment}"
  description = "Grants secretsmanager:GetSecretValue on exactly the Azure service-principal secret (${local.azure_service_principal_secret_name})."
  policy      = data.aws_iam_policy_document.read_azure_service_principal[0].json

  tags = local.tags
}

data "aws_iam_policy_document" "read_registry_credentials" {
  count = var.create_standalone_read_policies ? 1 : 0

  statement {
    sid       = "ReadRegistryCredentialsSecret"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.registry_credentials.arn]
  }
}

resource "aws_iam_policy" "read_registry_credentials" {
  count = var.create_standalone_read_policies ? 1 : 0

  name        = "${var.name_prefix}-read-registry-credentials-secret-${var.environment}"
  description = "Grants secretsmanager:GetSecretValue on exactly the registry credentials secret (${local.registry_credentials_secret_name})."
  policy      = data.aws_iam_policy_document.read_registry_credentials[0].json

  tags = local.tags
}
