variable "environment" {
  description = <<-EOT
    Environment or deploy-target name these secrets belong to (e.g. "dev"). Used to namespace
    secret names/tags so multiple environments never collide within the same account.
  EOT
  type        = string

  validation {
    condition     = length(var.environment) > 0
    error_message = "environment must not be empty."
  }
}

variable "name_prefix" {
  description = "Prefix applied to every secret name/tag created by this module (e.g. \"daf-phase1\")."
  type        = string
  default     = "daf-phase1"
}

# ---------------------------------------------------------------------------
# Encryption (create-or-reuse KMS key, matching modules/state-backend's and
# modules/dynamodb-tables' pattern)
# ---------------------------------------------------------------------------

variable "create_kms_key" {
  description = <<-EOT
    Whether this module creates a dedicated KMS key for secret encryption. Set to false and
    supply kms_key_arn to reuse an existing key instead (e.g. a key already created by another
    module).
  EOT
  type        = bool
  default     = true
}

variable "kms_key_arn" {
  description = "ARN of an existing KMS key to use for secret encryption. Required (and only used) when create_kms_key = false."
  type        = string
  default     = null

  validation {
    condition     = var.create_kms_key || var.kms_key_arn != null
    error_message = "kms_key_arn must be set when create_kms_key = false."
  }
}

variable "kms_key_deletion_window_in_days" {
  description = "Deletion window (in days) for the KMS key created by this module. Ignored when create_kms_key = false."
  type        = number
  default     = 30
}

# ---------------------------------------------------------------------------
# Secret name overrides
#
# All four names default to "<name_prefix>-<purpose>-<environment>". Overriding lets a caller
# match an existing naming convention or avoid a collision with a secret created outside this
# module.
# ---------------------------------------------------------------------------

variable "github_token_secret_name" {
  description = <<-EOT
    Name of the Secrets Manager secret holding the DevOps agent's GitHub token (PR-open scope).
    Defaults to "<name_prefix>-github-token-<environment>" when left null.
  EOT
  type        = string
  default     = null
}

variable "pr_reviewer_github_token_secret_name" {
  description = <<-EOT
    Name of the Secrets Manager secret holding the PR-Reviewer agent's GitHub token
    (read-only scope). MUST be a distinct secret from `github_token_secret_name` above — DevOps
    needs a token scoped to open pull requests, PR-Reviewer needs a separate, read-only-scoped
    token that can never reach a merge/approve-capable credential (see agent-iam-roles module
    README). Defaults to "<name_prefix>-pr-reviewer-github-token-<environment>" when left null.
  EOT
  type        = string
  default     = null
}

variable "azure_service_principal_secret_name" {
  description = <<-EOT
    Name of the Secrets Manager secret holding the Azure service-principal credentials
    (JSON: clientId, clientSecret, tenantId) used by the Discovery agent's Azure MCP connector.
    Defaults to "<name_prefix>-azure-service-principal-<environment>" when left null.
  EOT
  type        = string
  default     = null
}

variable "registry_credentials_secret_name" {
  description = <<-EOT
    Name of the Secrets Manager secret holding container-registry credentials (JSON:
    username, password) used to push/pull the synthetic app's container image
    (Task 14.5's build/deploy workflow). Defaults to
    "<name_prefix>-registry-credentials-<environment>" when left null.
  EOT
  type        = string
  default     = null
}

# ---------------------------------------------------------------------------
# Initial secret version values
#
# NONE of these are real production credentials. Terraform only ever writes a placeholder
# `aws_secretsmanager_secret_version` so the secret has a valid initial SecretString (Secrets
# Manager requires at least one version to exist for GetSecretValue to succeed) — every real
# value is populated out-of-band (manually, or by a separate secure rotation/CI process) after
# `terraform apply`, and Terraform never manages that value going forward (see main.tf's
# `lifecycle { ignore_changes = [secret_string] }` on each version resource). All four variables
# are marked sensitive so a placeholder value is never printed in plan/apply output, even though
# none of them should ever hold a real secret.
# ---------------------------------------------------------------------------

variable "github_token_placeholder" {
  description = <<-EOT
    Placeholder initial value for the DevOps GitHub token secret. NOT the real token — real
    rotation happens out-of-band (manual `aws secretsmanager put-secret-value`, or a separate
    secure CI/rotation process), never via `terraform apply`. Terraform ignores subsequent
    changes to this value (see main.tf), so applying this module again will not clobber a
    real value that has since been populated out-of-band.
  EOT
  type        = string
  default     = "REPLACE_ME_OUT_OF_BAND"
  sensitive   = true
}

variable "pr_reviewer_github_token_placeholder" {
  description = "Placeholder initial value for the PR-Reviewer GitHub token secret. See github_token_placeholder for the out-of-band rotation note."
  type        = string
  default     = "REPLACE_ME_OUT_OF_BAND"
  sensitive   = true
}

variable "azure_service_principal_placeholder" {
  description = <<-EOT
    Placeholder initial JSON value for the Azure service-principal secret. Must (like the real
    value) be a JSON object with clientId/clientSecret/tenantId fields, since
    `CredentialsClient.get_secret_fields` (Task 4.1) parses this secret's SecretString as JSON.
    NOT real credentials — see github_token_placeholder for the out-of-band rotation note.
  EOT
  type        = string
  default     = <<-EOT
    {"clientId": "REPLACE_ME_OUT_OF_BAND", "clientSecret": "REPLACE_ME_OUT_OF_BAND", "tenantId": "REPLACE_ME_OUT_OF_BAND"}
  EOT
  sensitive   = true
}

variable "registry_credentials_placeholder" {
  description = <<-EOT
    Placeholder initial JSON value for the container-registry credentials secret. Must (like the
    real value) be a JSON object with username/password fields, since
    `CredentialsClient.get_secret_fields` (Task 4.1) parses this secret's SecretString as JSON.
    NOT real credentials — see github_token_placeholder for the out-of-band rotation note.
  EOT
  type        = string
  default     = <<-EOT
    {"username": "REPLACE_ME_OUT_OF_BAND", "password": "REPLACE_ME_OUT_OF_BAND"}
  EOT
  sensitive   = true
}

# ---------------------------------------------------------------------------
# Recovery window (soft-delete)
# ---------------------------------------------------------------------------

variable "recovery_window_in_days" {
  description = <<-EOT
    Number of days Secrets Manager retains a deleted secret before permanent deletion (soft-delete
    window), applied to all four secrets. Set to 0 to force immediate deletion instead (useful for
    short-lived scratch/test environments only — this permanently and immediately destroys the
    secret with no recovery window).
  EOT
  type        = number
  default     = 30

  validation {
    condition     = var.recovery_window_in_days == 0 || (var.recovery_window_in_days >= 7 && var.recovery_window_in_days <= 30)
    error_message = "recovery_window_in_days must be 0 (immediate deletion) or between 7 and 30."
  }
}

# ---------------------------------------------------------------------------
# Standalone IAM policies (secondary/optional deliverable — see README)
# ---------------------------------------------------------------------------

variable "create_standalone_read_policies" {
  description = <<-EOT
    Whether this module also creates standalone `aws_iam_policy` resources (one per secret,
    granting only `secretsmanager:GetSecretValue` on that secret's ARN) for attachment to any
    consumer that is NOT one of the agent-iam-roles module's (Task 3.4) roles — e.g. a CI/CD
    role. Task 3.4's module builds its own inline read statements directly from this module's
    ARN outputs for the 7 agent roles, so these standalone policies are not needed for that
    integration path; they exist only as a convenience for other/future consumers. Defaults to
    false since no such consumer exists yet in Phase 1.
  EOT
  type        = bool
  default     = false
}

variable "tags" {
  description = "Additional tags merged onto every resource created by this module."
  type        = map(string)
  default     = {}
}
