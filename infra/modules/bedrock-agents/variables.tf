variable "environment" {
  description = <<-EOT
    Environment or deploy-target name these agents belong to (e.g. "dev"). Used to namespace
    agent names/tags so multiple environments never collide within the same account.
  EOT
  type        = string

  validation {
    condition     = length(var.environment) > 0
    error_message = "environment must not be empty."
  }
}

variable "name_prefix" {
  description = "Prefix applied to every agent name/tag created by this module (e.g. \"daf-phase1\")."
  type        = string
  default     = "daf-phase1"
}

variable "tags" {
  description = "Additional tags merged onto every resource created by this module."
  type        = map(string)
  default     = {}
}

# ---------------------------------------------------------------------------
# Task 3.1 — Bedrock Guardrails wiring
# ---------------------------------------------------------------------------

variable "guardrail_id" {
  description = "ID of the Bedrock Guardrail (Task 3.1's `bedrock-guardrails` module output `guardrail_id`) attached to every agent's `guardrail_configuration`."
  type        = string
}

variable "guardrail_version" {
  description = <<-EOT
    Version of the Bedrock Guardrail to attach (Task 3.1's `bedrock-guardrails` module output
    `guardrail_published_version`, falling back to "DRAFT" only for local iteration — production
    should always reference a published, immutable version).
  EOT
  type        = string
  default     = "DRAFT"
}

# ---------------------------------------------------------------------------
# Task 3.4 — per-agent IAM execution role ARNs
# ---------------------------------------------------------------------------

variable "agent_role_arns" {
  description = <<-EOT
    Map of agent key -> IAM role ARN, for the 5 core agents this module creates (Task 13's
    Discovery, DevOps, Security, Modernization, Portfolio Assessment agents). Supervisor and
    PR-Reviewer are out of scope for this module. Keys must be exactly: "discovery", "devops",
    "security", "modernization", "portfolio-assessment" — matching Task 3.4's agent-iam-roles
    module `role_arns` output keys, e.g.:

      agent_role_arns = {
        discovery             = module.agent_iam_roles.role_arns["discovery"]
        devops                = module.agent_iam_roles.role_arns["devops"]
        security              = module.agent_iam_roles.role_arns["security"]
        modernization         = module.agent_iam_roles.role_arns["modernization"]
        portfolio-assessment  = module.agent_iam_roles.role_arns["portfolio-assessment"]
      }
  EOT
  type        = map(string)

  validation {
    condition = length(setsubtract(
      ["discovery", "devops", "security", "modernization", "portfolio-assessment"],
      keys(var.agent_role_arns)
    )) == 0
    error_message = "agent_role_arns must include all 5 core agent keys: discovery, devops, security, modernization, portfolio-assessment."
  }
}

# ---------------------------------------------------------------------------
# Foundation models per tier (source design.md §5.2/§5.4 ModelTier: Haiku/Sonnet/Opus)
# ---------------------------------------------------------------------------

variable "foundation_model_ids" {
  description = <<-EOT
    Map of model tier ("haiku", "sonnet", "opus") -> Bedrock foundation-model ID (or cross-region
    inference profile ID) used as each agent's `foundation_model`. Every agent is created against
    its design.md §5.2 default tier (Discovery/DevOps -> Haiku, Security/Modernization/Portfolio
    Assessment -> Sonnet); Sonnet/Opus escalation at runtime is handled by the Router (Task 7),
    not by re-provisioning the agent resource itself.
  EOT
  type        = map(string)

  validation {
    condition     = length(setsubtract(["haiku", "sonnet", "opus"], keys(var.foundation_model_ids))) == 0
    error_message = "foundation_model_ids must include all 3 tiers: haiku, sonnet, opus."
  }
}

# ---------------------------------------------------------------------------
# Task 3.2 — Knowledge Base association (Security/Modernization/Portfolio Assessment agents)
# ---------------------------------------------------------------------------

variable "knowledge_base_id" {
  description = <<-EOT
    ID of the Bedrock Knowledge Base (Task 3.2's `bedrock-knowledge-base` module output
    `knowledge_base_id`) associated with the Security, Modernization, and Portfolio Assessment
    agents per design.md's agent/tool table (S3/KB MCP). Set to null to skip KB association
    (e.g. before the knowledge base is populated).
  EOT
  type        = string
  default     = null
}

variable "knowledge_base_description" {
  description = "Description passed to each agent's knowledge base association, shown to the model to explain when to retrieve from it."
  type        = string
  default     = "Corporate knowledge base of architecture standards, migration patterns, and prior assessment artifacts."
}

# ---------------------------------------------------------------------------
# Agent instructions (Phase 1: minimal, one per core agent)
# ---------------------------------------------------------------------------

variable "agent_instructions" {
  description = <<-EOT
    Map of agent key -> the Bedrock Agent's `instruction` string. Falls back to a minimal
    per-agent default instruction (see locals.tf) for any key omitted from this map, so Phase 1
    callers can override just one agent's instruction without repeating the others.
  EOT
  type        = map(string)
  default     = {}
}

variable "idle_session_ttl_seconds" {
  description = "Idle session TTL (seconds) for every agent. AWS default/min is 60s, max 3600s."
  type        = number
  default     = 1800
}
