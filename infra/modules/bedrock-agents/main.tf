locals {
  agent_name_prefix = "${var.name_prefix}-${var.environment}"

  # Default foundation-model tier per agent, matching backend/src/daf/router/policy.py's
  # TASK_MODEL_POLICY (design.md §5.2): Discovery/DevOps default to Haiku, Security/Modernization/
  # Portfolio Assessment default to Sonnet. Runtime escalation (Haiku -> Sonnet -> Opus) is
  # handled by the Router (Task 7) per-invocation, not by re-provisioning this agent resource.
  agent_default_tier = {
    discovery            = "haiku"
    devops               = "haiku"
    security             = "sonnet"
    modernization        = "sonnet"
    portfolio-assessment = "sonnet"
  }

  default_instructions = {
    discovery            = "You are the Discovery agent for the DAF platform. Collect and reason over Azure resource inventory to build a migration-relevant asset map."
    devops               = "You are the DevOps agent for the DAF platform. Execute infrastructure and CI/CD operations (Terraform, GitHub Actions) on behalf of an approved migration run."
    security             = "You are the Security agent for the DAF platform. Review proposed changes and existing resources for security findings against corporate standards in the knowledge base."
    modernization        = "You are the Modernization agent for the DAF platform. Recommend AWS-native modernization plans grounded in AWS documentation and the corporate knowledge base."
    portfolio-assessment = "You are the Portfolio Assessment agent for the DAF platform. Assess application portfolios for migration readiness using the corporate knowledge base."
  }

  agent_instructions = {
    for k in keys(local.agent_default_tier) :
    k => lookup(var.agent_instructions, k, local.default_instructions[k])
  }

  # Security, Modernization, and Portfolio Assessment agents use S3/KB MCP per design.md's
  # agent/tool table; Discovery and DevOps do not associate the knowledge base in Phase 1.
  kb_associated_agents = ["security", "modernization", "portfolio-assessment"]

  tags = merge(var.tags, {
    Environment = var.environment
    Purpose     = "bedrock-agent"
  })
}

# ---------------------------------------------------------------------------
# Bedrock Agents — one per core agent (Task 13.7)
#
# Each agent is attached to its own least-privilege IAM execution role (Task 3.4) and the shared
# Bedrock Guardrail (Task 3.1). Supervisor and PR-Reviewer agents are out of scope for this
# module (see var.agent_role_arns validation).
# ---------------------------------------------------------------------------

resource "aws_bedrockagent_agent" "this" {
  for_each = local.agent_default_tier

  agent_name                  = "${local.agent_name_prefix}-${each.key}"
  agent_resource_role_arn     = var.agent_role_arns[each.key]
  foundation_model            = var.foundation_model_ids[local.agent_default_tier[each.key]]
  instruction                 = local.agent_instructions[each.key]
  idle_session_ttl_in_seconds = var.idle_session_ttl_seconds

  guardrail_configuration {
    guardrail_identifier = var.guardrail_id
    guardrail_version    = var.guardrail_version
  }

  tags = merge(local.tags, {
    Name  = "${local.agent_name_prefix}-${each.key}"
    Agent = each.key
  })
}

# ---------------------------------------------------------------------------
# Knowledge Base association — Security, Modernization, Portfolio Assessment agents only.
# Skipped entirely when var.knowledge_base_id is null (KB not yet populated).
# ---------------------------------------------------------------------------

resource "aws_bedrockagent_agent_knowledge_base_association" "this" {
  for_each = var.knowledge_base_id == null ? {} : toset(local.kb_associated_agents)

  agent_id             = aws_bedrockagent_agent.this[each.key].agent_id
  agent_version        = "DRAFT"
  description          = var.knowledge_base_description
  knowledge_base_id    = var.knowledge_base_id
  knowledge_base_state = "ENABLED"
}

# ---------------------------------------------------------------------------
# Action groups — one placeholder action group per agent (Phase 1).
#
# LIMITATION (see README.md): no Lambda action-group executors exist in this codebase yet, so
# every action group is created DISABLED with a minimal inline OpenAPI schema. Wiring a real
# `action_group_executor { lambda = ... }` and re-enabling (`action_group_state = "ENABLED"`) is
# a follow-up once Task 13's agent-invocation Lambdas exist.
# ---------------------------------------------------------------------------

resource "aws_bedrockagent_agent_action_group" "this" {
  for_each = local.agent_default_tier

  action_group_name = "${each.key}-actions"
  agent_id          = aws_bedrockagent_agent.this[each.key].agent_id
  agent_version     = "DRAFT"

  # Safe-by-default: no executor is wired yet, so the action group must stay DISABLED (the AWS
  # provider otherwise requires a valid action_group_executor for an ENABLED group).
  action_group_state = "DISABLED"

  api_schema {
    payload = jsonencode({
      openapi = "3.0.0"
      info = {
        title       = "${each.key}-actions (placeholder)"
        version     = "1.0.0"
        description = "Placeholder OpenAPI schema. No operations are defined until this agent's Lambda action-group executor is implemented."
      }
      paths = {}
    })
  }
}
