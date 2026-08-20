variable "environment" {
  description = <<-EOT
    Environment or deploy-target name this memory store belongs to (e.g. "dev"). Used to
    namespace the memory name/tags so multiple environments never collide within the same
    account.
  EOT
  type        = string

  validation {
    condition     = length(var.environment) > 0
    error_message = "environment must not be empty."
  }
}

variable "name_prefix" {
  description = "Prefix applied to the memory name and tags created by this module (e.g. \"daf-phase1\")."
  type        = string
  default     = "daf-phase1"
}

variable "memory_name" {
  description = <<-EOT
    Name of the AgentCore Memory resource. Defaults to "<name_prefix>_memory_<environment>"
    (underscored, not hyphenated) when left null, since `awscc_bedrockagentcore_memory.name` must
    match `^[a-zA-Z][a-zA-Z0-9_]{0,47}$` (letters/digits/underscore only, max 48 chars — no
    hyphens, unlike most other DAF Phase 1 resource names).
  EOT
  type        = string
  default     = null
}

variable "description" {
  description = "Description of the memory's purpose, surfaced in the Bedrock console."
  type        = string
  default     = "DAF Phase 1 AgentCore Memory: per-run working memory (short-term) summarized and evicted into long-term memory when a run closes (Requirement 9.4)."
}

# ---------------------------------------------------------------------------
# Short-term memory (per-run working memory)
#
# AgentCore Memory does not expose a separate "short-term retention" knob from "long-term
# retention" — `event_expiry_duration` governs how long raw events (the short-term / per-run
# working set) are retained before they age out, per the CloudFormation `AWS::BedrockAgentCore::
# Memory` reference (Minimum 3, Maximum 365 days). The pipeline's post-invocation
# `Memory.summarizeAndEvict` step (Task 10.3) is expected to have already turned any events worth
# keeping into long-term memory records (via the configured strategies below) well before this
# expiry elapses — see this module's README "How Task 10.3 is expected to interact with this
# store".
# ---------------------------------------------------------------------------

variable "event_expiry_duration" {
  description = <<-EOT
    Number of days raw short-term memory events (the current run's working set) are retained
    before they expire, per Requirement 9.4's "per-run" framing. Must be between 3 and 365 days
    (AWS API limit). Phase 1 default of 7 days is intentionally short: `summarizeAndEvict` (Task
    10.3) runs synchronously when a run closes, so raw events are not expected to outlive the run
    itself by more than a few days of grace before AWS reaps them.
  EOT
  type        = number
  default     = 7

  validation {
    condition     = var.event_expiry_duration >= 3 && var.event_expiry_duration <= 365
    error_message = "event_expiry_duration must be between 3 and 365 days (AWS AgentCore Memory API limit)."
  }
}

variable "encryption_key_arn" {
  description = "Optional KMS key ARN used to encrypt the memory's events and memory records at rest. Leave null to use AgentCore's default (AWS-owned key) encryption."
  type        = string
  default     = null
}

# ---------------------------------------------------------------------------
# Long-term memory strategies (summarize-and-evict target)
#
# Each entry configures one built-in AgentCore memory strategy. Requirement 9.4 only requires
# that closed-run working memory be "summarized and evicted" into long-term memory, which the
# SUMMARIZATION strategy type directly satisfies; SEMANTIC/USER_PREFERENCE/EPISODIC are additional
# built-in strategy types the same Memory resource can host for richer cross-run recall and are
# included here as opt-in, not required, extensions.
#
# NOTE: the CUSTOM strategy type (self-managed extraction/consolidation pipelines, or built-in
# strategies overridden with a caller-supplied model/prompt) is intentionally NOT exposed by this
# variable. It requires materially more configuration (model IDs, prompt overrides, and/or a
# self-managed S3/SNS delivery pipeline) than Phase 1 needs. Extend this module's main.tf/
# variables.tf if a later phase needs it.
# ---------------------------------------------------------------------------

variable "memory_strategies" {
  description = <<-EOT
    Long-term memory strategies attached to this Memory resource. Each entry's `type` must be one
    of "SEMANTIC", "SUMMARIZATION", "USER_PREFERENCE", or "EPISODIC" (see note above re: CUSTOM).
    `namespaces` and `namespace_templates` control where extracted long-term records are stored;
    at least one of the two should normally be set for a strategy to be useful, but neither is
    enforced as required here since AWS accepts either, both, or (rarely) neither.

    Defaults to a single SUMMARIZATION strategy scoped per-run (`/summaries/{actorId}/
    {sessionId}`), directly satisfying Requirement 9.4's "summarized ... into AgentCore long-term
    memory" clause with no further configuration required.
  EOT
  type = list(object({
    type                = string
    name                = string
    description         = optional(string)
    namespaces          = optional(list(string))
    namespace_templates = optional(list(string))
  }))
  default = [
    {
      type        = "SUMMARIZATION"
      name        = "RunSummarizer"
      description = "Summarizes a run's working memory on close (Requirement 9.4 summarize-and-evict), keyed per run/session."
      namespaces  = ["/summaries/{actorId}/{sessionId}"]
    },
  ]

  validation {
    condition = alltrue([
      for s in var.memory_strategies : contains(["SEMANTIC", "SUMMARIZATION", "USER_PREFERENCE", "EPISODIC"], s.type)
    ])
    error_message = "Each memory_strategies[*].type must be one of SEMANTIC, SUMMARIZATION, USER_PREFERENCE, EPISODIC (CUSTOM is not supported by this module — see variables.tf)."
  }
}

variable "indexed_keys" {
  description = <<-EOT
    Metadata keys indexed for filtering on retrieval (e.g. RetrieveMemoryRecords metadata
    filters). Each entry's `type` must be one of "STRING", "STRINGLIST", "NUMBER". Empty by
    default — add entries as agents adopt structured metadata on their memory records.
  EOT
  type = list(object({
    key  = string
    type = string
  }))
  default = []

  validation {
    condition = alltrue([
      for k in var.indexed_keys : contains(["STRING", "STRINGLIST", "NUMBER"], k.type)
    ])
    error_message = "Each indexed_keys[*].type must be one of STRING, STRINGLIST, NUMBER."
  }
}

# ---------------------------------------------------------------------------
# Memory execution role
#
# Only required when a strategy needs AgentCore to invoke a Bedrock model on the caller's behalf
# (built-in-with-overrides / CUSTOM strategies using a caller-chosen model or prompt). Phase 1's
# default strategy list above uses plain built-in strategies (no per-strategy model override), so
# this defaults to NOT creating a role. Set create_memory_execution_role = true (or pass an
# existing execution_role_arn) only if a future strategy override needs it.
# ---------------------------------------------------------------------------

variable "create_memory_execution_role" {
  description = "Whether to create an IAM execution role trusted by bedrock-agentcore.amazonaws.com for AgentCore to invoke Bedrock models on this memory's behalf (needed only for strategy overrides that specify a model)."
  type        = bool
  default     = false
}

variable "memory_execution_role_arn" {
  description = "ARN of an existing IAM execution role to use instead of creating one. Only used when create_memory_execution_role = false and a role is otherwise needed; leave null if no strategy override needs a role."
  type        = string
  default     = null
}

# ---------------------------------------------------------------------------
# Agent read/write access policy
#
# A standalone aws_iam_policy (not attached to any role by this module) scoped to exactly this
# memory's data-plane actions, intended to be attached to each agent's own least-privilege IAM
# role from Task 3.4 (per-agent IAM roles) — this module does not itself create or own agent
# roles.
# ---------------------------------------------------------------------------

variable "create_agent_access_policy" {
  description = "Whether to create the aws_iam_policy exposing read/write access to this memory store for attachment to agent roles (Task 3.4)."
  type        = bool
  default     = true
}

variable "agent_read_actions" {
  description = "bedrock-agentcore data-plane read actions granted by the agent access policy (retrieval side of Memory.summarizeAndEvict and general recall)."
  type        = list(string)
  default = [
    "bedrock-agentcore:GetEvent",
    "bedrock-agentcore:ListEvents",
    "bedrock-agentcore:GetMemoryRecord",
    "bedrock-agentcore:ListMemoryRecords",
    "bedrock-agentcore:RetrieveMemoryRecords",
  ]
}

variable "agent_write_actions" {
  description = "bedrock-agentcore data-plane write actions granted by the agent access policy (write side of Memory.summarizeAndEvict — recording the closed run's working-memory events)."
  type        = list(string)
  default = [
    "bedrock-agentcore:CreateEvent",
    "bedrock-agentcore:DeleteEvent",
  ]
}

variable "tags" {
  description = "Additional tags merged onto every resource created by this module."
  type        = map(string)
  default     = {}
}
