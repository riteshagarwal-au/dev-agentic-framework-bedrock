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

module "networking" {
  source      = "./modules/networking"
  environment = var.environment
  name_prefix = var.project_tag
}

module "ecs_fargate_target" {
  source             = "./modules/ecs-fargate-target"
  environment        = var.environment
  name_prefix        = var.project_tag
  vpc_id             = module.networking.vpc_id
  private_subnet_ids = module.networking.private_subnet_ids
}

# Trusts the TARGET APP's own repo (not this DAF repo) — its container-deploy.yml workflow is
# what pushes images to ECR and updates the ECS service created above (design.md §7.3
# deterministic CI/CD path, gated by HitlGateType.CLOUD_DEPLOY on the target repo's side).
module "github_oidc" {
  source      = "./modules/github-oidc"
  environment = var.environment
  github_org  = "riteshagarwal-au"
  github_repo = "appmigration-daf"

  allowed_subject_patterns = [
    "repo:riteshagarwal-au/appmigration-daf:environment:cloud-deploy-approval",
  ]

  state_bucket_arn         = "arn:aws:s3:::daf-tfstate-dev-669076482267"
  state_bucket_kms_key_arn = "arn:aws:kms:ap-southeast-2:669076482267:key/3007fc05-ec31-42ff-bce6-44891023b841"

  ecr_repository_arns         = [module.ecs_fargate_target.ecr_repository_arn]
  ecs_cluster_arns            = [module.ecs_fargate_target.cluster_arn]
  ecs_service_arns            = [module.ecs_fargate_target.service_arn]
  ecs_task_definition_arns    = [module.ecs_fargate_target.task_definition_family_arn_pattern]
  ecs_task_execution_role_arn = module.ecs_fargate_target.task_execution_role_arn
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

module "portal_hosting" {
  source      = "./modules/portal-hosting"
  environment = var.environment
  name_prefix = var.project_tag
}

module "cognito_auth" {
  source        = "./modules/cognito-auth"
  environment   = var.environment
  name_prefix   = var.project_tag
  callback_urls = [module.portal_hosting.portal_url]
  logout_urls   = [module.portal_hosting.portal_url]
}

module "portal_api" {
  source                      = "./modules/portal-api"
  environment                 = var.environment
  name_prefix                 = var.project_tag
  backend_src_dir             = "${path.module}/../backend/src"
  backend_site_packages_dir   = "/tmp/daf-lambda-deps"
  run_state_table_name        = module.dynamodb_tables.run_state_table_name
  run_state_table_arn         = module.dynamodb_tables.run_state_table_arn
  run_counters_table_name     = module.dynamodb_tables.run_counters_table_name
  run_counters_table_arn      = module.dynamodb_tables.run_counters_table_arn
  gate_ticket_table_name      = module.dynamodb_tables.gate_ticket_table_name
  gate_ticket_table_arn       = module.dynamodb_tables.gate_ticket_table_arn
  hitl_state_machine_arn      = module.hitl_gate_state_machine.state_machine_arn
  dynamodb_kms_key_arn        = module.dynamodb_tables.kms_key_arn
  cognito_user_pool_client_id = module.cognito_auth.user_pool_client_id
  cognito_issuer_url          = module.cognito_auth.issuer_url
  cors_allowed_origins        = [module.portal_hosting.portal_url]
}
