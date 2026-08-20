# ---------------------------------------------------------------------------
# agent-iam-roles
#
# Provisions one distinct, least-privilege IAM role per DAF Phase 1 agent, per Requirements 2.3
# and 11.1:
#   - Requirement 2.3: "EACH core agent SHALL run under its own dedicated least-privilege IAM
#     role, distinct from the Supervisor's role and from every other agent's role."
#   - Requirement 11.1: "EACH agent and worker SHALL run under its own least-privilege IAM role;
#     no two agents SHALL share a role, and the Supervisor's role SHALL NOT include
#     migration-action permissions."
#
# Design choice — hybrid for_each + per-agent blocks:
#   The 7 roles share identical *structure* (trust policy shape, naming, tagging, the baseline
#   Bedrock model-invoke grant every agent needs), so that shared structure is a single
#   for_each-keyed set of resources below. But the 7 roles' *permission* sets differ enough in
#   shape (different resource ARNs, different AWS service action families, some agents getting
#   zero extra statements at all) that forcing them into one generic templated policy document
#   would obscure, not clarify, each agent's distinct least-privilege scope — and would make the
#   "Supervisor explicitly excludes migration-action permissions" property harder to see by
#   inspection. So each agent's *extra* permissions (beyond the shared Bedrock baseline) are their
#   own named `aws_iam_policy_document`/`aws_iam_role_policy` pair below, one per agent. This
#   keeps "distinct policy per agent" naturally visible in the code (supporting Task 3.5's
#   no-two-agents-share-a-policy-document validation) while still avoiding 7x duplication of the
#   trust-policy/role/tagging boilerplate.
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  region     = data.aws_region.current.name
  account_id = data.aws_caller_identity.current.account_id

  agent_keys = [
    "supervisor",
    "discovery",
    "devops",
    "security",
    "modernization",
    "portfolio-assessment",
    "pr-reviewer",
  ]

  # Confused-deputy prevention (per AWS guidance: always include both aws:SourceAccount and
  # aws:SourceArn on a Bedrock service-role trust policy). Bootstrapping problem: Task 13.7
  # creates the actual Bedrock Agent resources that assume these roles, and this module (Task
  # 3.4) runs before that, so the specific agent ID isn't known yet. Default to a same-account,
  # same-region wildcard pattern per agent; var.agent_source_arn_patterns lets a caller tighten
  # any individual agent's pattern to its real agent ID once Task 13.7 has created it.
  default_source_arn_pattern = ["arn:aws:bedrock:${local.region}:${local.account_id}:agent/*"]

  agent_source_arn_patterns = {
    for k in local.agent_keys :
    k => lookup(var.agent_source_arn_patterns, k, local.default_source_arn_pattern)
  }

  foundation_model_arns  = coalesce(var.foundation_model_arns, ["arn:aws:bedrock:${local.region}::foundation-model/*"])
  inference_profile_arns = coalesce(var.inference_profile_arns, ["arn:aws:bedrock:${local.region}:${local.account_id}:inference-profile/*"])

  role_name = { for k in local.agent_keys : k => "${var.name_prefix}-${k}-agent-role-${var.environment}" }

  common_tags = { for k in local.agent_keys : k => merge(var.tags, {
    Name        = local.role_name[k]
    Environment = var.environment
    Agent       = k
    Purpose     = "daf-agent-execution-role"
  }) }

  # A data.aws_iam_policy_document with zero rendered `statement` blocks is invalid, so the
  # per-agent role_policy resources below are only created (count = 1) once at least one of that
  # agent's optional input ARNs is non-null. Until then, that agent's role carries only the
  # shared Bedrock model-invoke/guardrail baseline policies above.
  discovery_has_permissions = var.artifacts_bucket_arn != null || var.azure_sp_secret_arn != null
  devops_has_permissions    = var.artifacts_bucket_arn != null || var.github_token_secret_arn != null
}

# ---------------------------------------------------------------------------
# Shared structure: one trust policy + one role per agent (for_each)
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "trust" {
  for_each = toset(local.agent_keys)

  statement {
    sid     = "BedrockAgentAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = local.agent_source_arn_patterns[each.key]
    }
  }
}

resource "aws_iam_role" "agent" {
  for_each = toset(local.agent_keys)

  name               = local.role_name[each.key]
  assume_role_policy = data.aws_iam_policy_document.trust[each.key].json
  description        = "Least-privilege execution role for the DAF ${each.key} agent (Requirements 2.3, 11.1). Distinct role and policy document from every other agent's role, including the Supervisor's."

  tags = local.common_tags[each.key]
}

# ---------------------------------------------------------------------------
# Shared baseline: every agent role can invoke Bedrock foundation models / inference profiles.
# This is the ONLY grant the Supervisor role receives (see the "supervisor" section below,
# which intentionally adds nothing migration-related).
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "bedrock_model_invoke" {
  statement {
    sid    = "BedrockModelInvocation"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = concat(local.foundation_model_arns, local.inference_profile_arns)
  }

  statement {
    sid    = "BedrockInferenceProfileMetadata"
    effect = "Allow"
    actions = [
      "bedrock:GetInferenceProfile",
      "bedrock:GetFoundationModel",
    ]
    resources = ["*"] # read-only metadata calls; no resource-level ARN scoping supported.
  }
}

resource "aws_iam_role_policy" "bedrock_model_invoke" {
  for_each = toset(local.agent_keys)

  name   = "${local.role_name[each.key]}-bedrock-model-invoke"
  role   = aws_iam_role.agent[each.key].id
  policy = data.aws_iam_policy_document.bedrock_model_invoke.json
}

# ---------------------------------------------------------------------------
# Shared, optional: ApplyGuardrail (only when var.guardrail_arn is supplied, e.g. after Task 3.1
# has been applied). Applying a guardrail to a model call is not a migration action — every agent
# including the Supervisor is permitted this grant.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "apply_guardrail" {
  count = var.guardrail_arn == null ? 0 : 1

  statement {
    sid    = "BedrockApplyGuardrail"
    effect = "Allow"
    actions = [
      "bedrock:ApplyGuardrail",
    ]
    resources = [var.guardrail_arn]
  }
}

resource "aws_iam_role_policy" "apply_guardrail" {
  for_each = var.guardrail_arn == null ? toset([]) : toset(local.agent_keys)

  name   = "${local.role_name[each.key]}-apply-guardrail"
  role   = aws_iam_role.agent[each.key].id
  policy = data.aws_iam_policy_document.apply_guardrail[0].json
}

# ---------------------------------------------------------------------------
# Supervisor — orchestrates only (design.md Component 1). Deliberately receives NO grant beyond
# the shared Bedrock model-invoke/guardrail baseline above: no S3, no DynamoDB, no Secrets
# Manager, no Terraform/ECS/IaC-apply-equivalent permission, no destructive action of any kind.
# This is what satisfies Requirement 11.1's "the Supervisor's role SHALL NOT include
# migration-action permissions" at the IAM level — there is no migration-action statement to
# exclude because no statement beyond model invocation exists on this role at all.
#
# The only additional, OPTIONAL grant this role can receive is bedrock:InvokeAgent/GetAgentAlias
# against the persistent core agents' aliases, if Bedrock's native multi-agent collaboration
# mechanism is used for star-topology brokering (design.md Component 1) instead of/alongside
# plain application-code orchestration. This still does not grant any cloud-resource-mutating
# permission — it only lets the Supervisor hand a task to a spoke agent, which itself executes
# under its own distinct least-privilege role.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "supervisor_invoke_agent" {
  count = length(var.supervisor_collaborator_agent_alias_arns) == 0 ? 0 : 1

  statement {
    sid    = "SupervisorInvokeCollaboratorAgents"
    effect = "Allow"
    actions = [
      "bedrock:InvokeAgent",
      "bedrock:GetAgentAlias",
    ]
    resources = var.supervisor_collaborator_agent_alias_arns
  }
}

resource "aws_iam_role_policy" "supervisor_invoke_agent" {
  count = length(var.supervisor_collaborator_agent_alias_arns) == 0 ? 0 : 1

  name   = "${local.role_name["supervisor"]}-invoke-collaborator-agents"
  role   = aws_iam_role.agent["supervisor"].id
  policy = data.aws_iam_policy_document.supervisor_invoke_agent[0].json
}

# ---------------------------------------------------------------------------
# Discovery — Azure MCP + Filesystem MCP are not AWS IAM concerns (no AWS API call governs
# access to an external Azure API or a local filesystem tool). What IAM actually governs for this
# agent: read/write on its own ArtifactRef key prefix in the artifacts bucket (its collected
# inventory output), and read access to the Azure service-principal credential secret it needs to
# authenticate the Azure MCP connector (Task 4.1/4.3).
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "discovery" {
  dynamic "statement" {
    for_each = var.artifacts_bucket_arn == null ? [] : [1]
    content {
      sid    = "DiscoveryArtifactsReadWrite"
      effect = "Allow"
      actions = [
        "s3:GetObject",
        "s3:PutObject",
      ]
      resources = ["${var.artifacts_bucket_arn}/discovery/*"]
    }
  }

  dynamic "statement" {
    for_each = var.artifacts_bucket_arn == null ? [] : [1]
    content {
      sid       = "DiscoveryArtifactsListOwnPrefix"
      effect    = "Allow"
      actions   = ["s3:ListBucket"]
      resources = [var.artifacts_bucket_arn]
      condition {
        test     = "StringLike"
        variable = "s3:prefix"
        values   = ["discovery/*"]
      }
    }
  }

  dynamic "statement" {
    for_each = var.azure_sp_secret_arn == null ? [] : [1]
    content {
      sid       = "DiscoveryReadAzureServicePrincipalSecret"
      effect    = "Allow"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = [var.azure_sp_secret_arn]
    }
  }
}

resource "aws_iam_role_policy" "discovery" {
  count = local.discovery_has_permissions ? 1 : 0

  name   = "${local.role_name["discovery"]}-permissions"
  role   = aws_iam_role.agent["discovery"].id
  policy = data.aws_iam_policy_document.discovery.json
}

# ---------------------------------------------------------------------------
# DevOps — never applies/deploys directly (Requirement 2.5, 7.1: opens a PR via GitHub MCP,
# GitHub Actions applies later, gated by HITL). This role therefore gets NO ecs:UpdateService,
# NO terraform-apply-equivalent state-bucket access, and NO ECR push — those all belong to the
# github-oidc module's CI/CD role (Task 2.2), which is a distinct identity that only GitHub
# Actions assumes after the PR-merge + infra-apply HITL gates are approved. What this role does
# get: read/write on its own ArtifactRef key prefix (generated Terraform/workflow files staged
# before being opened as a PR) and read access to the GitHub token secret used to open that PR.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "devops" {
  dynamic "statement" {
    for_each = var.artifacts_bucket_arn == null ? [] : [1]
    content {
      sid    = "DevOpsArtifactsReadWrite"
      effect = "Allow"
      actions = [
        "s3:GetObject",
        "s3:PutObject",
      ]
      resources = ["${var.artifacts_bucket_arn}/devops/*"]
    }
  }

  dynamic "statement" {
    for_each = var.artifacts_bucket_arn == null ? [] : [1]
    content {
      sid       = "DevOpsArtifactsListOwnPrefix"
      effect    = "Allow"
      actions   = ["s3:ListBucket"]
      resources = [var.artifacts_bucket_arn]
      condition {
        test     = "StringLike"
        variable = "s3:prefix"
        values   = ["devops/*"]
      }
    }
  }

  dynamic "statement" {
    for_each = var.github_token_secret_arn == null ? [] : [1]
    content {
      sid       = "DevOpsReadGitHubTokenSecret"
      effect    = "Allow"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = [var.github_token_secret_arn]
    }
  }
}

resource "aws_iam_role_policy" "devops" {
  count = local.devops_has_permissions ? 1 : 0

  name   = "${local.role_name["devops"]}-permissions"
  role   = aws_iam_role.agent["devops"].id
  policy = data.aws_iam_policy_document.devops.json
}

# ---------------------------------------------------------------------------
# Security — evaluates a migration/Terraform plan and returns a pass result or findings; never
# itself approves or blocks the plan (Requirement 2.6). Gets read-only KB retrieve access plus a
# read-only set of IAM/Config/SecurityHub APIs to inspect the account's actual policy/compliance
# posture. No write/apply permission anywhere in this statement set.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "security" {
  dynamic "statement" {
    for_each = var.knowledge_base_arn == null ? [] : [1]
    content {
      sid    = "SecurityKnowledgeBaseRetrieve"
      effect = "Allow"
      actions = [
        "bedrock:Retrieve",
        "bedrock:RetrieveAndGenerate",
      ]
      resources = [var.knowledge_base_arn]
    }
  }

  statement {
    sid       = "SecurityReadOnlyComplianceChecks"
    effect    = "Allow"
    actions   = var.security_readonly_actions
    resources = ["*"] # all actions here are read-only list/describe/get calls with no resource-level ARN support.
  }
}

resource "aws_iam_role_policy" "security" {
  name   = "${local.role_name["security"]}-permissions"
  role   = aws_iam_role.agent["security"].id
  policy = data.aws_iam_policy_document.security.json
}

# ---------------------------------------------------------------------------
# Modernization — AWS Documentation MCP is not an AWS IAM concern (it's an MCP-level tool, not an
# AWS API call). What IAM actually governs: read-only KB retrieve access to the corporate KB
# (Task 3.2), used alongside AWS Docs MCP per the KB-vs-AWS-Docs conflict-detection logic
# (Task 13.6, Requirement 9.2).
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "modernization" {
  dynamic "statement" {
    for_each = var.knowledge_base_arn == null ? [] : [1]
    content {
      sid    = "ModernizationKnowledgeBaseRetrieve"
      effect = "Allow"
      actions = [
        "bedrock:Retrieve",
        "bedrock:RetrieveAndGenerate",
      ]
      resources = [var.knowledge_base_arn]
    }
  }
}

resource "aws_iam_role_policy" "modernization" {
  count = var.knowledge_base_arn == null ? 0 : 1

  name   = "${local.role_name["modernization"]}-permissions"
  role   = aws_iam_role.agent["modernization"].id
  policy = data.aws_iam_policy_document.modernization.json
}

# ---------------------------------------------------------------------------
# Portfolio Assessment — complexity/risk/value categorization from KB guidance only; no other
# AWS API access needed (design.md Component 5 table: "S3/KB MCP" is its only tool).
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "portfolio_assessment" {
  dynamic "statement" {
    for_each = var.knowledge_base_arn == null ? [] : [1]
    content {
      sid    = "PortfolioAssessmentKnowledgeBaseRetrieve"
      effect = "Allow"
      actions = [
        "bedrock:Retrieve",
        "bedrock:RetrieveAndGenerate",
      ]
      resources = [var.knowledge_base_arn]
    }
  }
}

resource "aws_iam_role_policy" "portfolio_assessment" {
  count = var.knowledge_base_arn == null ? 0 : 1

  name   = "${local.role_name["portfolio-assessment"]}-permissions"
  role   = aws_iam_role.agent["portfolio-assessment"].id
  policy = data.aws_iam_policy_document.portfolio_assessment.json
}

# ---------------------------------------------------------------------------
# PR-Reviewer (on-demand) — advisory-only: posts a comment via a read-only GitHub MCP connection,
# never merges or approves (Requirement 7.3, 9.5). Gets read access to a read-only-scoped GitHub
# token secret ONLY — deliberately a distinct secret ARN from the DevOps agent's
# github_token_secret_arn (see that variable's description), so this role's IAM grant can never
# reach a merge/approve-capable credential even indirectly. No write-capable GitHub credential or
# any other AWS permission is granted to this role.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "pr_reviewer" {
  dynamic "statement" {
    for_each = var.pr_reviewer_github_token_secret_arn == null ? [] : [1]
    content {
      sid       = "PrReviewerReadReadOnlyGitHubTokenSecret"
      effect    = "Allow"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = [var.pr_reviewer_github_token_secret_arn]
    }
  }
}

resource "aws_iam_role_policy" "pr_reviewer" {
  count = var.pr_reviewer_github_token_secret_arn == null ? 0 : 1

  name   = "${local.role_name["pr-reviewer"]}-permissions"
  role   = aws_iam_role.agent["pr-reviewer"].id
  policy = data.aws_iam_policy_document.pr_reviewer.json
}
