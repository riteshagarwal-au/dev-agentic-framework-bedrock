# DAF Phase 1 root module.
#
# This root module composes the submodules under infra/modules/ (state backend, GitHub OIDC
# federation, networking, Bedrock resources, DynamoDB tables, Step Functions HITL gate state
# machine, ECS Fargate target infra). No resources are declared directly here.
#
# Submodule wiring is added incrementally by later tasks:
#   - Task 2.1: modules/state-backend
#   - Task 2.2: modules/github-oidc
#   - Task 2.3: modules/networking
#   - Task 2.4: modules/hitl-gate-state-machine
#   - Task 3.x: modules/bedrock-* (guardrails, knowledge-base, agentcore-memory, agent-iam-roles)
#   - Task 5.1: modules/dynamodb-tables
#   - Task 14.3: modules/ecs-fargate-target
#
# See infra/modules/README.md for the convention each submodule follows.

module "github_oidc" {
  source      = "./modules/github-oidc"
  environment = var.environment
  github_org  = "riteshagarwal-au"
  github_repo = "dev-agentic-framework-bedrock"
}

module "networking" {
  source      = "./modules/networking"
  environment = var.environment
  name_prefix = var.project_tag
}

module "dynamodb_tables" {
  source      = "./modules/dynamodb-tables"
  environment = var.environment
  name_prefix = var.project_tag
}

module "bedrock_guardrails" {
  source      = "./modules/bedrock-guardrails"
  environment = var.environment
  name_prefix = var.project_tag
}

module "hitl_gate_state_machine" {
  source = "./modules/hitl-gate-state-machine"
}

module "agent_iam_roles" {
  source        = "./modules/agent-iam-roles"
  environment   = var.environment
  name_prefix   = var.project_tag
  guardrail_arn = module.bedrock_guardrails.guardrail_arn
}
