data "aws_partition" "current" {}
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  # awscc_bedrockagentcore_memory.name must match ^[a-zA-Z][a-zA-Z0-9_]{0,47}$ — underscores only,
  # no hyphens — so the default here deliberately diverges from every other module's
  # "<name_prefix>-<thing>-<environment>" (hyphenated) convention.
  memory_name = coalesce(var.memory_name, "${replace(var.name_prefix, "-", "_")}_memory_${replace(var.environment, "-", "_")}")

  tags = merge(var.tags, {
    Name        = local.memory_name
    Environment = var.environment
    Purpose     = "bedrock-agentcore-memory"
  })

  # Maps each supported built-in strategy `type` to the awscc_bedrockagentcore_memory schema's
  # corresponding single-nested-block attribute name under memory_strategies[*]. CUSTOM is
  # intentionally omitted (see variables.tf note on var.memory_strategies).
  strategy_block_key_by_type = {
    SEMANTIC        = "semantic_memory_strategy"
    SUMMARIZATION   = "summary_memory_strategy"
    USER_PREFERENCE = "user_preference_memory_strategy"
    EPISODIC        = "episodic_memory_strategy"
  }

  memory_strategies = [
    for s in var.memory_strategies : {
      "${local.strategy_block_key_by_type[s.type]}" = {
        name                = s.name
        description         = s.description
        namespaces          = s.namespaces
        namespace_templates = s.namespace_templates
      }
    }
  ]

  memory_execution_role_arn = var.create_memory_execution_role ? aws_iam_role.memory_execution[0].arn : var.memory_execution_role_arn
}

# ---------------------------------------------------------------------------
# Bedrock AgentCore Memory
#
# Provisioned via the AWS Cloud Control provider's awscc_bedrockagentcore_memory resource, NOT
# hashicorp/aws's `aws_bedrockagentcore_memory` — see this module's README "Provider version
# note" for why: the repo's pinned `hashicorp/aws ~> 5.0` (validated at 5.100.0) has no
# `aws_bedrockagentcore_*` resources at all in that provider major version; AgentCore Memory
# support landed in `hashicorp/aws` only in v6.18.0, well past this repo's `~> 5.0` ceiling.
#
# Short-term (per-run) retention: event_expiry_duration (Requirement 9.4 "per-run" framing).
# Long-term retention/strategies: memory_strategies (Requirement 9.4 "summarized ... into
# AgentCore long-term memory"), consumed by the post-invocation Memory.summarizeAndEvict step
# (Task 10.3) — see README "How Task 10.3 is expected to interact with this store".
# ---------------------------------------------------------------------------

resource "awscc_bedrockagentcore_memory" "this" {
  name                      = local.memory_name
  description               = var.description
  event_expiry_duration     = var.event_expiry_duration
  encryption_key_arn        = var.encryption_key_arn
  memory_execution_role_arn = local.memory_execution_role_arn
  memory_strategies         = local.memory_strategies
  indexed_keys              = var.indexed_keys

  tags = local.tags
}

# ---------------------------------------------------------------------------
# Optional memory execution role
#
# Only needed when a strategy override requires AgentCore to invoke a Bedrock model on this
# memory's behalf (see variables.tf var.create_memory_execution_role). Trust policy per AWS's
# documented AgentCore execution-role pattern: trusted by the bedrock-agentcore.amazonaws.com
# service principal, scoped via aws:SourceAccount/aws:SourceArn to this specific memory to guard
# against the cross-service confused-deputy problem.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "memory_execution_trust" {
  count = var.create_memory_execution_role ? 1 : 0

  statement {
    sid     = "AgentCoreMemoryAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${data.aws_partition.current.partition}:bedrock-agentcore:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:memory/*"]
    }
  }
}

resource "aws_iam_role" "memory_execution" {
  count = var.create_memory_execution_role ? 1 : 0

  name               = "${local.memory_name}-execution"
  assume_role_policy = data.aws_iam_policy_document.memory_execution_trust[0].json
  description        = "Execution role assumed by Bedrock AgentCore to invoke models on behalf of memory ${local.memory_name}'s strategy overrides."

  tags = merge(local.tags, {
    Name = "${local.memory_name}-execution"
  })
}

data "aws_iam_policy_document" "memory_execution_invoke_model" {
  count = var.create_memory_execution_role ? 1 : 0

  statement {
    sid    = "AgentCoreMemoryInvokeModel"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    # Bedrock model invocation actions do not support resource-level scoping to a specific
    # memory; scope is bounded by this role's trust policy (only assumable by AgentCore acting on
    # this account's memories) instead.
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "memory_execution_invoke_model" {
  count = var.create_memory_execution_role ? 1 : 0

  name   = "${local.memory_name}-invoke-model"
  role   = aws_iam_role.memory_execution[0].id
  policy = data.aws_iam_policy_document.memory_execution_invoke_model[0].json
}

# ---------------------------------------------------------------------------
# Agent read/write access policy
#
# Standalone policy (not attached to any role here) scoped to exactly this memory's bedrock-
# agentcore data-plane actions, resource-scoped to this memory's ARN. Attach to each agent's own
# least-privilege IAM role from Task 3.4 — this module does not create or own agent roles, only
# exposes the policy document/ARN for them to attach.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "agent_memory_access" {
  count = var.create_agent_access_policy ? 1 : 0

  statement {
    sid       = "AgentCoreMemoryReadWrite"
    effect    = "Allow"
    actions   = concat(var.agent_read_actions, var.agent_write_actions)
    resources = [awscc_bedrockagentcore_memory.this.memory_arn]
  }
}

resource "aws_iam_policy" "agent_memory_access" {
  count = var.create_agent_access_policy ? 1 : 0

  name        = "${local.memory_name}-agent-access"
  description = "Read/write access to AgentCore Memory ${local.memory_name}, for attachment to each agent's least-privilege IAM role (Task 3.4)."
  policy      = data.aws_iam_policy_document.agent_memory_access[0].json

  tags = merge(local.tags, {
    Name = "${local.memory_name}-agent-access"
  })
}
