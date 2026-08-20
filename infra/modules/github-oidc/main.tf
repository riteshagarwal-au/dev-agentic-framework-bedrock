locals {
  oidc_provider_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : var.oidc_provider_arn

  # IAM condition values must be exact string matches for the `sub` claim, so StringLike is used
  # (not StringEquals) to allow wildcard patterns (e.g. tag globs) inside allowed_subject_patterns.
  github_actions_audience = "sts.amazonaws.com"
}

# ---------------------------------------------------------------------------
# GitHub Actions OIDC identity provider.
#
# One IAM OIDC provider per issuer URL per AWS account — set create_oidc_provider = false and
# pass oidc_provider_arn when a provider for token.actions.githubusercontent.com already exists
# in this account (e.g. created by a different environment's instance of this module).
# ---------------------------------------------------------------------------

resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 1 : 0

  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = [local.github_actions_audience]
  thumbprint_list = var.github_thumbprint_list

  tags = merge(var.tags, {
    Name        = "github-actions-oidc"
    Environment = var.environment
  })
}

# ---------------------------------------------------------------------------
# IAM role assumable by GitHub Actions via OIDC, scoped to a specific repo and set of
# branch/environment/workflow subject patterns.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "trust" {
  statement {
    sid     = "GitHubActionsOidcAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = [local.github_actions_audience]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = var.allowed_subject_patterns
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name                 = var.role_name
  assume_role_policy   = data.aws_iam_policy_document.trust.json
  max_session_duration = var.max_session_duration_seconds
  description          = "Assumed by GitHub Actions (${var.github_org}/${var.github_repo}) via OIDC federation for DAF CI/CD. Requirement 7.8 (no long-lived AWS access keys)."

  tags = merge(var.tags, {
    Name        = var.role_name
    Environment = var.environment
  })
}

# ---------------------------------------------------------------------------
# Scoped permissions policy: ECR push, Terraform apply on the DAF state backend, ECS service
# update. No permission in this policy is broader than what the deterministic CI/CD path (Task
# 14.4/14.5) actually needs.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "permissions" {
  # --- ECR: push container images built by the CI/CD workflow (Task 14.5) -------------------
  statement {
    sid    = "EcrAuth"
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken",
    ]
    resources = ["*"] # ecr:GetAuthorizationToken does not support resource-level scoping.
  }

  statement {
    sid    = "EcrPush"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
    ]
    resources = var.ecr_repository_arns
  }

  # --- Terraform apply against the DAF state backend (Task 2.1) -----------------------------
  statement {
    sid    = "TerraformStateBucketAccess"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket",
    ]
    resources = [
      var.state_bucket_arn,
      "${var.state_bucket_arn}/*",
    ]
  }

  statement {
    sid    = "TerraformStateLockfile"
    effect = "Allow"
    actions = [
      # S3-native state locking (use_lockfile = true) creates/removes a `.tflock` companion
      # object using conditional writes/deletes — no DynamoDB lock table (see state-backend
      # module README).
      "s3:DeleteObject",
    ]
    resources = ["${var.state_bucket_arn}/*"]
  }

  statement {
    sid    = "TerraformStateKmsAccess"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:Encrypt",
      "kms:GenerateDataKey",
      "kms:DescribeKey",
    ]
    resources = [var.state_bucket_kms_key_arn]
  }

  # --- ECS service update (Task 14.5 deploy step) -------------------------------------------
  statement {
    sid    = "EcsServiceUpdate"
    effect = "Allow"
    actions = [
      "ecs:UpdateService",
      "ecs:DescribeServices",
    ]
    # ecs:UpdateService/DescribeServices support resource-level permissions on the `service`
    # resource type (ARN format: arn:aws:ecs:region:account:service/cluster-name/service-name).
    resources = var.ecs_service_arns

    # Belt-and-suspenders: also require the call to target one of the allowed clusters.
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = var.ecs_cluster_arns
    }
  }

  statement {
    sid    = "EcsTaskDefinitionAccess"
    effect = "Allow"
    actions = [
      "ecs:DescribeTaskDefinition",
    ]
    resources = var.ecs_task_definition_arns
  }

  statement {
    sid    = "EcsRegisterTaskDefinition"
    effect = "Allow"
    actions = [
      # ecs:RegisterTaskDefinition has no resource-level ARN support in IAM — it must be
      # granted with resources = ["*"]. Scope is instead bounded by this role's overall
      # permission set (ECR/ECS/Terraform-state only) and its OIDC trust policy.
      "ecs:RegisterTaskDefinition",
    ]
    resources = ["*"]
  }

  dynamic "statement" {
    for_each = var.ecs_task_execution_role_arn == null ? [] : [var.ecs_task_execution_role_arn]
    content {
      sid    = "EcsPassExecutionRole"
      effect = "Allow"
      actions = [
        "iam:PassRole",
      ]
      resources = [statement.value]

      condition {
        test     = "StringEquals"
        variable = "iam:PassedToService"
        values   = ["ecs-tasks.amazonaws.com"]
      }
    }
  }
}

resource "aws_iam_role_policy" "github_actions" {
  name   = "${var.role_name}-permissions"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.permissions.json
}
