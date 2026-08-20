variable "environment" {
  description = "Environment or deploy-target name this OIDC role belongs to (e.g. \"dev\"). Used only for resource naming/tagging."
  type        = string

  validation {
    condition     = length(var.environment) > 0
    error_message = "environment must not be empty."
  }
}

variable "create_oidc_provider" {
  description = <<-EOT
    Whether this module creates the GitHub Actions OIDC identity provider
    (`token.actions.githubusercontent.com`). An AWS account can only have one IAM OIDC provider
    per issuer URL, so set this to `false` (and supply `oidc_provider_arn`) when a provider for
    GitHub Actions already exists in the account (e.g. created by another environment/module
    instance).
  EOT
  type        = bool
  default     = true
}

variable "oidc_provider_arn" {
  description = "ARN of an existing GitHub Actions OIDC provider to use when create_oidc_provider = false. Required (and only used) in that case."
  type        = string
  default     = null

  validation {
    condition     = var.create_oidc_provider || var.oidc_provider_arn != null
    error_message = "oidc_provider_arn must be set when create_oidc_provider = false."
  }
}

variable "github_thumbprint_list" {
  description = <<-EOT
    TLS certificate thumbprints for token.actions.githubusercontent.com. AWS no longer verifies
    this value for GitHub's OIDC provider (GitHub Actions OIDC tokens are validated against the
    provider's published JWKS instead), but the IAM API still requires a non-empty list at
    creation time. Only used when create_oidc_provider = true.
  EOT
  type        = list(string)
  default     = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

variable "github_org" {
  description = "GitHub organization (or user) that owns the repository allowed to assume this role."
  type        = string

  validation {
    condition     = length(var.github_org) > 0
    error_message = "github_org must not be empty."
  }
}

variable "github_repo" {
  description = "GitHub repository name (without the org/ prefix) allowed to assume this role."
  type        = string

  validation {
    condition     = length(var.github_repo) > 0
    error_message = "github_repo must not be empty."
  }
}

variable "allowed_subject_patterns" {
  description = <<-EOT
    List of GitHub Actions OIDC token `sub` claim patterns allowed to assume this role, scoped to
    `var.github_org/var.github_repo`. Each entry is matched with IAM's `StringLike` condition
    operator (supports `*`/`?` wildcards) against the full `sub` claim, e.g.:
      - "repo:my-org/my-repo:ref:refs/heads/main"        (a specific branch)
      - "repo:my-org/my-repo:environment:production"     (a specific GitHub environment)
      - "repo:my-org/my-repo:ref:refs/tags/v*"            (a tag pattern)
    There is no default — callers MUST supply at least one explicit pattern. Callers MUST NOT
    pass a bare "repo:my-org/my-repo:*" wildcard — that would allow any branch/PR/workflow in the
    repo to assume the role, defeating the branch/workflow scoping this module is meant to
    enforce.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.allowed_subject_patterns) > 0
    error_message = "allowed_subject_patterns must contain at least one entry."
  }

  validation {
    condition = alltrue([
      for p in var.allowed_subject_patterns : startswith(p, "repo:${var.github_org}/${var.github_repo}:")
    ])
    error_message = "Every entry in allowed_subject_patterns must start with \"repo:${var.github_org}/${var.github_repo}:\" — this role must not be assumable by a different repository."
  }
}

variable "role_name" {
  description = "Name of the IAM role assumed by GitHub Actions via OIDC."
  type        = string
  default     = "daf-github-actions-oidc"
}

variable "max_session_duration_seconds" {
  description = "Maximum session duration (seconds) for the assumed role."
  type        = number
  default     = 3600
}

# ---------------------------------------------------------------------------
# Scoped permissions: state backend (Task 2.1)
# ---------------------------------------------------------------------------

variable "state_bucket_arn" {
  description = "ARN of the Terraform remote-state S3 bucket (state-backend module output bucket_arn) this role is allowed to read/write for `terraform apply`."
  type        = string
}

variable "state_bucket_kms_key_arn" {
  description = "ARN of the KMS key protecting the Terraform state bucket (state-backend module output kms_key_arn) this role is allowed to use for state encryption/decryption."
  type        = string
}

# ---------------------------------------------------------------------------
# Scoped permissions: ECR push
# ---------------------------------------------------------------------------

variable "ecr_repository_arns" {
  description = "ARNs of the ECR repositories this role is allowed to push container images to."
  type        = list(string)

  validation {
    condition     = length(var.ecr_repository_arns) > 0
    error_message = "ecr_repository_arns must contain at least one ECR repository ARN."
  }
}

# ---------------------------------------------------------------------------
# Scoped permissions: ECS service update
# ---------------------------------------------------------------------------

variable "ecs_cluster_arns" {
  description = "ARNs of the ECS clusters this role is allowed to describe/update services on."
  type        = list(string)

  validation {
    condition     = length(var.ecs_cluster_arns) > 0
    error_message = "ecs_cluster_arns must contain at least one ECS cluster ARN."
  }
}

variable "ecs_service_arns" {
  description = "ARNs of the ECS services this role is allowed to update/describe (used to scope ecs:UpdateService/ecs:DescribeServices)."
  type        = list(string)

  validation {
    condition     = length(var.ecs_service_arns) > 0
    error_message = "ecs_service_arns must contain at least one ECS service ARN."
  }
}

variable "ecs_task_definition_arns" {
  description = <<-EOT
    ARNs (or ARN patterns, e.g. with a `:*` revision wildcard) of the ECS task definitions this
    role is allowed to register/describe as part of a service update/deploy.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.ecs_task_definition_arns) > 0
    error_message = "ecs_task_definition_arns must contain at least one ECS task definition ARN/pattern."
  }
}

variable "ecs_task_execution_role_arn" {
  description = <<-EOT
    ARN of the ECS task execution role (and/or task role) that this CI/CD role must be allowed to
    pass to ECS via iam:PassRole when registering a new task definition revision / updating a
    service. Set to null to omit the PassRole grant (e.g. if task definitions are pre-registered
    by another process and this role only ever calls ecs:UpdateService).
  EOT
  type        = string
  default     = null
}

variable "tags" {
  description = "Additional tags merged onto every resource created by this module."
  type        = map(string)
  default     = {}
}
