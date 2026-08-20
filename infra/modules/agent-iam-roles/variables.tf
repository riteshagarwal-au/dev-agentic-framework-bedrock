variable "environment" {
  description = <<-EOT
    Environment or deploy-target name these agent IAM roles belong to (e.g. "dev"). Used to
    namespace role names/tags so multiple environments never collide within the same account.
  EOT
  type        = string

  validation {
    condition     = length(var.environment) > 0
    error_message = "environment must not be empty."
  }
}

variable "name_prefix" {
  description = "Prefix applied to every role name/tag created by this module (e.g. \"daf-phase1\")."
  type        = string
  default     = "daf-phase1"
}

# ---------------------------------------------------------------------------
# Trust policy scoping (confused-deputy prevention)
# ---------------------------------------------------------------------------

variable "agent_source_arn_patterns" {
  description = <<-EOT
    Per-agent override of the `aws:SourceArn` `ArnLike` condition values on each role's trust
    policy, keyed by agent key (one of: supervisor, discovery, devops, security, modernization,
    portfolio-assessment, pr-reviewer).

    Bedrock recommends scoping a service role's trust policy to the specific agent resource ARN
    that assumes it (confused-deputy prevention, see
    https://docs.aws.amazon.com/bedrock/latest/userguide/agents-permissions.html — "as a best
    practice for security purposes, replace the * with specific agent IDs after you have created
    them"). This module has a bootstrapping/circular-dependency problem: the Bedrock Agent
    resources that will assume these roles are created by Task 13.7, which itself takes these
    roles' ARNs as an input — so the agent ARN cannot be known at the time this module first
    applies.

    Every agent key defaults (when omitted from this map) to a same-account/same-region wildcard
    pattern (`arn:aws:bedrock:<region>:<account-id>:agent/*`), combined with the `aws:SourceAccount`
    condition (always applied, not overridable) per AWS's "always include both conditions"
    guidance. Once Task 13.7 creates the actual agent and its ID is known, tighten this variable
    per-agent to `["arn:aws:bedrock:<region>:<account-id>:agent/<agent-id>"]` — this is a
    trust-policy-only update on the role (no replacement, no downtime for other roles).
  EOT
  type        = map(list(string))
  default     = {}
}

# ---------------------------------------------------------------------------
# Bedrock model access (shared by every agent role)
# ---------------------------------------------------------------------------

variable "foundation_model_arns" {
  description = <<-EOT
    Bedrock foundation-model ARNs (or ARN patterns) every agent role is permitted to invoke via
    `bedrock:InvokeModel`/`InvokeModelWithResponseStream`. Foundation-model ARNs have no account
    ID segment, so these are region-scoped, not account-scoped. Defaults to every foundation model
    in the current region — narrow this if Phase 1 is meant to pin specific model IDs (e.g. only
    the Haiku/Sonnet/Opus family actually used by the task->model policy table, Task 7.1).
  EOT
  type        = list(string)
  default     = null # computed from the current region when left null; see locals.tf
}

variable "inference_profile_arns" {
  description = <<-EOT
    Bedrock (cross-region/AU-CRIS) inference profile ARNs every agent role is permitted to invoke
    via `bedrock:InvokeModel`/`InvokeModelWithResponseStream`/`GetInferenceProfile`. Defaults to
    every inference profile in the current account/region — narrow this to the specific AU-CRIS
    profile ARNs once they are provisioned/known.
  EOT
  type        = list(string)
  default     = null # computed from the current account/region when left null; see locals.tf
}

variable "guardrail_arn" {
  description = <<-EOT
    ARN of the Bedrock Guardrail (Task 3.1's `bedrock-guardrails` module output `guardrail_arn`)
    every agent role needs `bedrock:ApplyGuardrail` permission for, per
    https://docs.aws.amazon.com/bedrock/latest/userguide/agents-permissions.html ("if you
    associate a guardrail with your agent, permissions to apply that guardrail"). Left `null`
    (the default) omits the ApplyGuardrail statement entirely, e.g. before Task 3.1 has been
    applied.
  EOT
  type        = string
  default     = null
}

# ---------------------------------------------------------------------------
# Knowledge Base access (Discovery excluded — see README; Security, Modernization,
# Portfolio Assessment need read-only Retrieve access, Task 3.2's KB module output)
# ---------------------------------------------------------------------------

variable "knowledge_base_arn" {
  description = <<-EOT
    ARN of the Bedrock Knowledge Base (Task 3.2's `bedrock-knowledge-base` module output) that
    the Security, Modernization, and Portfolio Assessment agent roles are granted read-only
    `bedrock:Retrieve`/`bedrock:RetrieveAndGenerate` access to. Left `null` (the default) omits
    the KB-retrieve statement for those three roles entirely, e.g. before Task 3.2 has been
    applied.
  EOT
  type        = string
  default     = null
}

# ---------------------------------------------------------------------------
# Artifact storage (Discovery, DevOps only — see README for why the other agents don't get a
# direct S3 grant here)
# ---------------------------------------------------------------------------

variable "artifacts_bucket_arn" {
  description = <<-EOT
    ARN of the S3 bucket used to store agent-produced/consumed `ArtifactRef` payloads (inventory,
    Terraform plans, etc.) — a separate bucket from the Terraform remote-state bucket
    (`state-backend` module) and not yet provisioned by an earlier task as of Task 3.4. Left
    `null` (the default) omits every S3 statement in this module entirely. Discovery and DevOps
    are each scoped to read/write only their own key prefix within this bucket
    (`discovery/*`, `devops/*` respectively) — never the whole bucket.
  EOT
  type        = string
  default     = null
}

# ---------------------------------------------------------------------------
# Secrets Manager access (Task 4.1/4.3 secret resources)
# ---------------------------------------------------------------------------

variable "azure_sp_secret_arn" {
  description = <<-EOT
    ARN of the Secrets Manager secret holding the Azure service-principal credentials (Task 4.3)
    that the Discovery agent role is granted `secretsmanager:GetSecretValue` access to. Left
    `null` (the default) omits the statement entirely, e.g. before Task 4.3 has been applied.
  EOT
  type        = string
  default     = null
}

variable "github_token_secret_arn" {
  description = <<-EOT
    ARN of the Secrets Manager secret holding the GitHub token (Task 4.3) used to open pull
    requests, that the DevOps agent role is granted `secretsmanager:GetSecretValue` access to.
    Left `null` (the default) omits the statement entirely, e.g. before Task 4.3 has been applied.

    This must be a distinct secret from `pr_reviewer_github_token_secret_arn` below — DevOps
    needs a token scoped to open pull requests; PR-Reviewer needs a separate, read-only-scoped
    token. Provisioning which underlying GitHub credential scope each secret actually holds is
    Task 4.3's job; this module only wires IAM read access to whichever secret ARN each agent is
    given.
  EOT
  type        = string
  default     = null
}

variable "pr_reviewer_github_token_secret_arn" {
  description = <<-EOT
    ARN of the Secrets Manager secret holding a read-only-scoped GitHub token (Task 4.3) that the
    PR-Reviewer agent role is granted `secretsmanager:GetSecretValue` access to. Must be a
    distinct secret ARN from `github_token_secret_arn` — see that variable's description. Left
    `null` (the default) omits the statement entirely.
  EOT
  type        = string
  default     = null
}

# ---------------------------------------------------------------------------
# Supervisor: optional multi-agent-collaboration InvokeAgent grant
# ---------------------------------------------------------------------------

variable "supervisor_collaborator_agent_alias_arns" {
  description = <<-EOT
    Bedrock agent-alias ARNs of the 5 persistent core agents that the Supervisor role is
    permitted to invoke via `bedrock:InvokeAgent`/`bedrock:GetAgentAlias`, if/when Bedrock native
    multi-agent collaboration is used for star-topology brokering (design.md Component 1). Left
    empty (the default) omits this statement entirely — the Supervisor role then carries no
    permission beyond `bedrock:InvokeModel`/inference-profile metadata/`ApplyGuardrail`, which is
    sufficient if the Supervisor's own orchestration logic (task decomposition, routing) runs as
    plain Lambda/application code calling each spoke's Bedrock Agent through the hook pipeline
    (Task 10.x) rather than through Bedrock's native collaborator mechanism.

    This is intentionally NOT the same permission as being allowed to perform a migration action
    — `bedrock:InvokeAgent` only lets the Supervisor hand a task to a spoke agent (which itself
    runs under its own distinct least-privilege role); it grants no S3/Terraform/ECS/Secrets
    Manager access whatsoever to the Supervisor's own role.
  EOT
  type        = list(string)
  default     = []
}

# ---------------------------------------------------------------------------
# Security agent: read-only compliance/policy check APIs
# ---------------------------------------------------------------------------

variable "security_readonly_actions" {
  description = <<-EOT
    Read-only IAM/Config/SecurityHub actions granted to the Security agent role for evaluating a
    migration/Terraform plan's policy and compliance posture (Requirement 2.6 — the Security
    Agent returns a pass result or findings and never itself approves/blocks the plan). All
    actions here are read-only (`Get*`/`List*`/`Describe*`/`Generate*ServiceLastAccessedDetails`)
    — no `Put`/`Create`/`Update`/`Delete` action belongs in this list.
  EOT
  type        = list(string)
  default = [
    "iam:GetRole",
    "iam:GetRolePolicy",
    "iam:GetPolicy",
    "iam:GetPolicyVersion",
    "iam:ListRolePolicies",
    "iam:ListAttachedRolePolicies",
    "iam:ListPolicies",
    "iam:GenerateServiceLastAccessedDetails",
    "iam:GetServiceLastAccessedDetails",
    "config:DescribeConfigRules",
    "config:DescribeComplianceByConfigRule",
    "config:GetComplianceDetailsByConfigRule",
    "config:DescribeConfigRuleEvaluationStatus",
    "securityhub:GetFindings",
    "securityhub:ListFindings",
    "securityhub:DescribeStandards",
    "securityhub:DescribeStandardsControls",
    "securityhub:GetEnabledStandards",
  ]
}

variable "tags" {
  description = "Additional tags merged onto every resource created by this module."
  type        = map(string)
  default     = {}
}
