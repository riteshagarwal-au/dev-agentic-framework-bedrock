# github-oidc

Provisions the GitHub Actions OIDC identity provider and a scoped IAM role that DAF's CI/CD
workflows assume to authenticate to AWS, per Requirement 7.8:

> GitHub Actions SHALL authenticate to AWS via OIDC federation to a scoped IAM role, and SHALL NOT
> use long-lived AWS access keys stored as Actions secrets.

## What this module creates

- An `aws_iam_openid_connect_provider` for `token.actions.githubusercontent.com` (audience
  `sts.amazonaws.com`), optional — set `create_oidc_provider = false` and pass
  `oidc_provider_arn` if a GitHub Actions OIDC provider already exists in this AWS account (an
  account can only have one OIDC provider per issuer URL).
- An IAM role (`aws_iam_role.github_actions`) with a trust policy that:
  - Only trusts the `token.actions.githubusercontent.com` federated principal.
  - Requires `aud = sts.amazonaws.com`.
  - Requires the token's `sub` claim to match one of `var.allowed_subject_patterns` — every
    pattern is validated at plan time to start with `repo:<github_org>/<github_repo>:`, so this
    role can never be assumed by a different repository, and callers must not pass a bare
    `repo:org/repo:*` wildcard (that would allow any branch/PR/workflow to assume the role).
- An inline IAM policy on that role granting **only**:
  - **ECR push**: `ecr:GetAuthorizationToken` (account-wide, as required by the API) plus
    `ecr:BatchCheckLayerAvailability` / `PutImage` / `InitiateLayerUpload` / `UploadLayerPart` /
    `CompleteLayerUpload` / etc. scoped to `var.ecr_repository_arns`.
  - **Terraform apply on the DAF state backend**: `s3:GetObject` / `PutObject` / `ListBucket` /
    `DeleteObject` (the last needed for the S3-native `.tflock` companion object under
    `use_lockfile = true`) scoped to `var.state_bucket_arn`, plus `kms:Decrypt` / `Encrypt` /
    `GenerateDataKey` / `DescribeKey` scoped to `var.state_bucket_kms_key_arn`. This grants state
    *access*, not blanket AWS admin — the actual resources a `terraform apply` can create/modify
    are governed by whatever IAM permissions the Terraform execution role/identity has for the
    target resources themselves (out of scope for this module; see Task 3.4 for per-agent roles
    and the root module's own provider credentials for the apply step's resource permissions).
  - **ECS service update**: `ecs:UpdateService` / `DescribeServices` scoped to
    `var.ecs_service_arns` (with an additional `ecs:cluster` condition requiring
    `var.ecs_cluster_arns`), `ecs:DescribeTaskDefinition` scoped to
    `var.ecs_task_definition_arns`, and `ecs:RegisterTaskDefinition` (no resource-level ARN
    support in IAM, so granted with `resources = ["*"]` — bounded by the role's overall
    permission set and trust policy, not by a resource ARN), plus an optional `iam:PassRole`
    grant restricted to `var.ecs_task_execution_role_arn` (only when non-null) and conditioned on
    `iam:PassedToService = ecs-tasks.amazonaws.com`.

No permission beyond these three groups is granted — this role cannot, for example, read/write
arbitrary S3 buckets, manage IAM, or touch resources outside the ECS clusters/services and ECR
repositories passed in.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `environment` | Environment/target name, used for naming/tagging only. | `string` | n/a (required) |
| `create_oidc_provider` | Whether to create the GitHub OIDC provider (false if one already exists in the account). | `bool` | `true` |
| `oidc_provider_arn` | Existing OIDC provider ARN, required when `create_oidc_provider = false`. | `string` | `null` |
| `github_thumbprint_list` | TLS thumbprint(s) required by the IAM API at provider-creation time (no longer verified by AWS for GitHub's provider). | `list(string)` | `["6938fd4d98bab03faadb97b34396831e3780aea1"]` |
| `github_org` | GitHub org/user that owns the allowed repo. | `string` | n/a (required) |
| `github_repo` | GitHub repo name (without the org prefix). | `string` | n/a (required) |
| `allowed_subject_patterns` | `sub`-claim `StringLike` patterns scoping which branch/environment/workflow may assume the role. Must all start with `repo:<github_org>/<github_repo>:`. | `list(string)` | n/a (required) |
| `role_name` | Name of the IAM role. | `string` | `"daf-github-actions-oidc"` |
| `max_session_duration_seconds` | Max STS session duration. | `number` | `3600` |
| `state_bucket_arn` | ARN of the Terraform state S3 bucket (state-backend module `bucket_arn` output). | `string` | n/a (required) |
| `state_bucket_kms_key_arn` | ARN of the KMS key protecting the state bucket (state-backend module `kms_key_arn` output). | `string` | n/a (required) |
| `ecr_repository_arns` | ECR repository ARN(s) this role may push images to. | `list(string)` | n/a (required) |
| `ecs_cluster_arns` | ECS cluster ARN(s) this role's service updates must target (`ecs:cluster` condition). | `list(string)` | n/a (required) |
| `ecs_service_arns` | ECS service ARN(s) this role may update/describe (resource-level scoping on `ecs:UpdateService`/`DescribeServices`). | `list(string)` | n/a (required) |
| `ecs_task_definition_arns` | ECS task definition ARN(s)/patterns this role may describe/register. | `list(string)` | n/a (required) |
| `ecs_task_execution_role_arn` | ECS task execution/task role this CI/CD role may `iam:PassRole` to ECS. Omit the grant by leaving this `null`. | `string` | `null` |
| `tags` | Extra tags merged onto all resources. | `map(string)` | `{}` |

## Outputs

| Name | Description |
|---|---|
| `oidc_provider_arn` | ARN of the GitHub Actions OIDC provider. |
| `role_arn` | ARN of the IAM role — this is what gets referenced in the GitHub Actions workflow's `role-to-assume`. |
| `role_name` | Name of the IAM role. |

## Usage

```hcl
module "github_oidc" {
  source = "../../modules/github-oidc"

  environment = var.environment

  github_org  = "my-org"
  github_repo = "daf"

  allowed_subject_patterns = [
    "repo:my-org/daf:ref:refs/heads/main",
    "repo:my-org/daf:environment:dev-infra-apply",
  ]

  state_bucket_arn         = module.state_backend.bucket_arn
  state_bucket_kms_key_arn = module.state_backend.kms_key_arn

  ecr_repository_arns = [module.ecr.repository_arn]

  ecs_cluster_arns           = [module.ecs_fargate_target.cluster_arn]
  ecs_service_arns           = [module.ecs_fargate_target.service_arn]
  ecs_task_definition_arns   = ["${module.ecs_fargate_target.task_definition_arn_prefix}:*"]
  ecs_task_execution_role_arn = module.ecs_fargate_target.task_execution_role_arn
}
```

## Example GitHub Actions workflow snippet

The workflow must declare `permissions: id-token: write` so the job can request an OIDC token,
and use `aws-actions/configure-aws-credentials` with `role-to-assume` set to this module's
`role_arn` output — no `aws-access-key-id`/`aws-secret-access-key` secrets are used anywhere.

```yaml
name: terraform-apply

on:
  workflow_dispatch:

permissions:
  id-token: write   # required to request the OIDC token
  contents: read

jobs:
  terraform-apply:
    runs-on: ubuntu-latest
    environment: dev-infra-apply   # matches an environment-scoped subject pattern, if used
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials via OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::123456789012:role/daf-github-actions-oidc
          aws-region: ap-southeast-2

      - name: Terraform apply
        run: terraform apply -auto-approve
        working-directory: infra
```

This is a dependency for the CI/CD workflows in Task 14.4 (`terraform apply`, gated by HITL) and
Task 14.5 (container build/push + ECS deploy).

## Requirements traceability

- Requirement 7.8: "GitHub Actions SHALL authenticate to AWS via OIDC federation to a scoped IAM
  role, and SHALL NOT use long-lived AWS access keys stored as Actions secrets." — this module is
  that scoped IAM role and its OIDC trust relationship; no AWS access key resources are created
  or referenced anywhere in this module.
