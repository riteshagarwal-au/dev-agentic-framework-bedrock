# infra/modules/bedrock-agents/

## Purpose

Creates a `aws_bedrockagent_agent` resource for each of the 5 core DAF agents (Discovery, DevOps,
Security, Modernization, Portfolio Assessment — **not** Supervisor or PR-Reviewer, which are out
of scope for Task 13), each attached to:

- Its own least-privilege IAM execution role, from Task 3.4's `agent-iam-roles` module
  (`var.agent_role_arns`).
- The shared Bedrock Guardrail from Task 3.1's `bedrock-guardrails` module
  (`var.guardrail_id` / `var.guardrail_version`).
- Its design.md §5.2 default foundation-model tier (Discovery/DevOps -> Haiku, Security/
  Modernization/Portfolio Assessment -> Sonnet), matching
  `backend/src/daf/router/policy.py`'s `TASK_MODEL_POLICY`. Runtime escalation
  (Haiku -> Sonnet -> Opus) is handled by the Router (Task 7) per-invocation, not by
  re-provisioning this agent resource.
- The corporate Knowledge Base from Task 3.2's `bedrock-knowledge-base` module, for the Security,
  Modernization, and Portfolio Assessment agents only (per design.md's agent/tool table),
  via `aws_bedrockagent_agent_knowledge_base_association`. Skipped entirely when
  `var.knowledge_base_id` is left `null`.

## Inputs

| Name | Description |
| --- | --- |
| `environment` | Deploy-target name (e.g. `"dev"`), namespaces agent names/tags. |
| `name_prefix` | Prefix applied to every agent name/tag (default `"daf-phase1"`). |
| `tags` | Additional tags merged onto every resource. |
| `guardrail_id` | Bedrock Guardrail ID (Task 3.1 `bedrock-guardrails` output `guardrail_id`). |
| `guardrail_version` | Guardrail version to attach (prefer Task 3.1's `guardrail_published_version` output over `"DRAFT"`). |
| `agent_role_arns` | Map of agent key -> IAM role ARN for the 5 core agents (Task 3.4 `agent-iam-roles` output `role_arns`, filtered to these 5 keys). |
| `foundation_model_ids` | Map of `"haiku"`/`"sonnet"`/`"opus"` -> Bedrock foundation-model ID or inference-profile ID. |
| `knowledge_base_id` | Task 3.2 `bedrock-knowledge-base` output `knowledge_base_id`, or `null` to skip KB association. |
| `knowledge_base_description` | Description shown to the model for the KB association. |
| `agent_instructions` | Optional per-agent instruction override map; falls back to a minimal per-agent default. |
| `idle_session_ttl_seconds` | Idle session TTL for every agent (default `1800`). |

## Outputs

- `agent_ids` / `agent_arns` — maps of agent key -> Bedrock Agent ID/ARN.
- `<agent>_agent_id` / `<agent>_agent_arn` — convenience per-agent accessors (discovery, devops,
  security, modernization, portfolio_assessment).
- `action_group_ids` — map of agent key -> placeholder action group ID.

## Known limitation: action groups are placeholders

Each agent gets exactly one `aws_bedrockagent_agent_action_group` resource (named
`"<agent-key>-actions"`), created with:

- `action_group_state = "DISABLED"` — no `action_group_executor` (Lambda) is wired yet, because
  the agent-invocation Lambdas for these 5 core agents don't exist in this codebase yet (they are
  a Task 13 follow-up, distinct from this Terraform task). The AWS provider requires a valid
  executor for an `ENABLED` action group, so `DISABLED` with a placeholder schema is the
  safe-by-default choice here.
- A minimal inline OpenAPI 3.0 schema with no operations (`paths = {}`), just enough to satisfy
  the resource's required `api_schema` argument.

**Follow-up work** (not part of Task 13.7): once each agent's Lambda action-group executor is
implemented, add an `action_group_executor { lambda = <lambda_arn> }` block, replace the
placeholder OpenAPI schema with the real operation definitions, and flip
`action_group_state = "ENABLED"`.

## Provider resource availability

This module targets `hashicorp/aws ~> 5.0`; the version currently pinned in this repo's
`.terraform.lock.hcl` is `5.100.0`, which supports `aws_bedrockagent_agent`,
`aws_bedrockagent_agent_action_group`, and `aws_bedrockagent_agent_knowledge_base_association`.

## Root wiring

**Not wired into `infra/main.tf` by this task.** Root wiring needs the Task 3.2 knowledge-base
module's output and a `foundation_model_ids` value that reflects the actual Bedrock model IDs
enabled for this AWS account/region (not yet confirmed) — see `infra/main.tf`'s existing
`bedrock_guardrails` / `agent_iam_roles` module blocks for the pattern to follow once those
values are known:

```hcl
module "bedrock_agents" {
  source        = "./modules/bedrock-agents"
  environment   = var.environment
  name_prefix   = var.project_tag
  guardrail_id  = module.bedrock_guardrails.guardrail_id
  agent_role_arns = {
    discovery             = module.agent_iam_roles.role_arns["discovery"]
    devops                = module.agent_iam_roles.role_arns["devops"]
    security              = module.agent_iam_roles.role_arns["security"]
    modernization         = module.agent_iam_roles.role_arns["modernization"]
    portfolio-assessment  = module.agent_iam_roles.role_arns["portfolio-assessment"]
  }
  foundation_model_ids = {
    haiku  = "anthropic.claude-3-5-haiku-20241022-v1:0"
    sonnet = "anthropic.claude-sonnet-4-5-20250929-v1:0"
    opus   = "anthropic.claude-opus-4-1-20250805-v1:0"
  }
}
```
