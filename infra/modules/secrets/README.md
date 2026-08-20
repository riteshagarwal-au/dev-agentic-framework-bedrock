# secrets

Provisions the 4 AWS Secrets Manager secrets Requirement 11.2 names explicitly, per
design.md "Security Considerations":

> "Secrets (GitHub token, Azure SP, registry creds) live only in Secrets Manager, injected at
> tool-call time — never in prompts/context/memory/logs."

> **Requirement 11.2**: "ALL credentials (GitHub token, Azure service principal, registry
> credentials) SHALL be stored in AWS Secrets Manager and injected at tool-call time only."

## What this module creates

| Secret | Shape | Consumer |
|---|---|---|
| `github_token` | Plain string | DevOps agent role (Task 3.4) — opens pull requests only (PR-open scope). |
| `pr_reviewer_github_token` | Plain string | PR-Reviewer agent role (Task 3.4) — a **separate** secret from `github_token`, read-only scope only. |
| `azure_service_principal` | JSON (`clientId`, `clientSecret`, `tenantId`) | Discovery agent role (Task 3.4) — authenticates the Azure MCP connector. |
| `registry_credentials` | JSON (`username`, `password`) | Not currently wired into any Task 3.4 agent role — see "Forward dependency" below. |

Each secret is:

- Encrypted with a KMS key, following the same create-or-reuse pattern as `modules/state-backend`
  and `modules/dynamodb-tables` (`create_kms_key = true` creates a dedicated key; set it `false`
  and pass `kms_key_arn` to reuse an existing key).
- Given an initial `aws_secretsmanager_secret_version` so `GetSecretValue` succeeds immediately
  after apply (Secrets Manager requires at least one version to exist).
- Soft-delete protected via `recovery_window_in_days` (default 30, matching typical production
  hygiene — set to 0 only in short-lived scratch/test environments where immediate, unrecoverable
  deletion is acceptable).

## Security note: these are NOT populated with real values by Terraform

Every initial secret version written by this module is a **placeholder** value
(`REPLACE_ME_OUT_OF_BAND` for the plain-string secrets; a JSON object with the same placeholder
string in each field for the JSON-structured secrets) — **never a real credential**. Concretely:

- The placeholder values are supplied via `sensitive = true` Terraform variables
  (`github_token_placeholder`, `pr_reviewer_github_token_placeholder`,
  `azure_service_principal_placeholder`, `registry_credentials_placeholder`), so even the
  placeholder never appears in plan/apply console output.
- Each `aws_secretsmanager_secret_version` resource has `lifecycle { ignore_changes =
  [secret_string] }`. This means: once the real credential is populated out-of-band (a manual
  `aws secretsmanager put-secret-value` call, or a separate secure rotation/CI process — **not**
  `terraform apply`), a later `terraform apply` of this module will **not** overwrite that real
  value back to the placeholder. Terraform only ever "wins" the very first version of each secret;
  every subsequent real-value rotation happens entirely outside Terraform's management.
- No Terraform state produced by this module ever contains a real GitHub token, Azure service
  principal secret, or registry password — only the placeholder string(s), which are also marked
  sensitive so they're redacted from CLI output.

**Rotating a real value**: use `aws secretsmanager put-secret-value --secret-id
<name-or-arn-from-outputs> --secret-string '<real value>'` (or your organization's secret rotation
tooling) after this module's first apply. Do not attempt to pass the real value into this module's
placeholder variables — they exist only to satisfy Secrets Manager's "at least one version"
requirement at creation time.

## How the 4 ARNs feed Task 3.4's agent-iam-roles module

Task 3.4's `agent-iam-roles` module already builds its own scoped `secretsmanager:GetSecretValue`
IAM statements when given a secret ARN — it takes exactly the ARNs this module outputs as its
own input variables:

| This module's output | Feeds `agent-iam-roles` variable | Granted to |
|---|---|---|
| `github_token_secret_arn` | `github_token_secret_arn` | DevOps agent role |
| `pr_reviewer_github_token_secret_arn` | `pr_reviewer_github_token_secret_arn` | PR-Reviewer agent role |
| `azure_service_principal_secret_arn` | `azure_sp_secret_arn` | Discovery agent role |
| `registry_credentials_secret_arn` | *(none — see "Forward dependency" below)* | — |

```hcl
module "secrets" {
  source      = "../../modules/secrets"
  environment = var.environment
}

module "agent_iam_roles" {
  source      = "../../modules/agent-iam-roles"
  environment = var.environment

  azure_sp_secret_arn                 = module.secrets.azure_service_principal_secret_arn
  github_token_secret_arn             = module.secrets.github_token_secret_arn
  pr_reviewer_github_token_secret_arn = module.secrets.pr_reviewer_github_token_secret_arn
}
```

This module deliberately creates `github_token` and `pr_reviewer_github_token` as **two separate**
`aws_secretsmanager_secret` resources (never one secret shared between DevOps and PR-Reviewer) —
`agent-iam-roles`' README explicitly calls out that these must be distinct secrets/credential
scopes, so that the PR-Reviewer role's read grant can never reach a merge/approve-capable
credential even indirectly.

### Secondary/optional deliverable: standalone read-only IAM policies

Because `agent-iam-roles` already builds its own read statements from this module's ARN outputs,
this module's *primary* job is secret creation + ARN outputs, not IAM policy authoring. For any
OTHER consumer that isn't one of Task 3.4's 7 agent roles (e.g. a future CI/CD role needing
`registry_credentials` access), set `create_standalone_read_policies = true` to also get one
`aws_iam_policy` per secret, each scoped to `secretsmanager:GetSecretValue` on exactly that
secret's ARN (output: `standalone_read_policy_arns`). Defaults to `false` since no such consumer
exists yet in Phase 1.

## Forward dependency: registry credentials

No agent role provisioned by Task 3.4 currently references `registry_credentials_secret_arn` —
none of the 7 agent roles need direct container-registry access. This secret's actual consumer is
Task 14.5's GitHub Actions workflow ("Write GitHub Actions workflow for container build/deploy to
ECS Fargate"), which will need to authenticate to the container registry when building/pushing the
synthetic app's image. That workflow either:

- Runs as the `github-oidc` module's (Task 2.2) CI/CD role and reads this secret via a scoped
  standalone policy (`create_standalone_read_policies = true`, attach
  `standalone_read_policy_arns.registry_credentials` to that role), or
- Uses OIDC-federated registry auth directly (e.g. ECR's `ecr:GetAuthorizationToken`, already
  granted to the `github-oidc` role) instead of a long-lived registry credential, in which case
  this secret may end up unused for the ECR case specifically and only relevant for a non-ECR
  registry.

This module provisions the secret and its ARN now so Task 14.5 has a concrete resource to wire
into once that workflow is written; no further action is needed here until then.

## What this module does NOT create

- The IAM roles that read these secrets — those are Task 3.4's `agent-iam-roles` module, which
  takes this module's ARN outputs as input.
- Any Secrets Manager rotation schedule/Lambda — Phase 1 rotation is manual/out-of-band (see
  "Security note" above); automated rotation is not in scope for Phase 1.
- The real credential values themselves, at any point, ever (see "Security note" above).

## Usage

```hcl
module "secrets" {
  source      = "../../modules/secrets"
  environment = var.environment
  name_prefix = "daf-phase1"
}

output "secret_arns" {
  value = module.secrets.secret_arns
}
```

### Reusing an existing KMS key instead of creating one

```hcl
module "secrets" {
  source         = "../../modules/secrets"
  environment    = var.environment
  create_kms_key = false
  kms_key_arn    = module.dynamodb_tables.kms_key_arn # or any other existing key
}
```

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `environment` | Environment/target name; namespaces secret names/tags. | `string` | n/a (required) |
| `name_prefix` | Prefix for generated secret names/tags. | `string` | `"daf-phase1"` |
| `create_kms_key` | Whether to create a dedicated KMS key. | `bool` | `true` |
| `kms_key_arn` | Existing KMS key ARN to reuse. Required when `create_kms_key = false`. | `string` | `null` |
| `kms_key_deletion_window_in_days` | KMS key deletion window. Ignored when `create_kms_key = false`. | `number` | `30` |
| `github_token_secret_name` | Override for the DevOps GitHub token secret name. | `string` | `null` (computed) |
| `pr_reviewer_github_token_secret_name` | Override for the PR-Reviewer GitHub token secret name. | `string` | `null` (computed) |
| `azure_service_principal_secret_name` | Override for the Azure SP secret name. | `string` | `null` (computed) |
| `registry_credentials_secret_name` | Override for the registry credentials secret name. | `string` | `null` (computed) |
| `github_token_placeholder` | Placeholder initial value (NOT a real token). Sensitive. | `string` | `"REPLACE_ME_OUT_OF_BAND"` |
| `pr_reviewer_github_token_placeholder` | Placeholder initial value (NOT a real token). Sensitive. | `string` | `"REPLACE_ME_OUT_OF_BAND"` |
| `azure_service_principal_placeholder` | Placeholder initial JSON value (NOT real credentials). Sensitive. | `string` | placeholder JSON |
| `registry_credentials_placeholder` | Placeholder initial JSON value (NOT real credentials). Sensitive. | `string` | placeholder JSON |
| `recovery_window_in_days` | Soft-delete recovery window for all 4 secrets. `0` or `7`-`30`. | `number` | `30` |
| `create_standalone_read_policies` | Whether to also create one standalone read-only `aws_iam_policy` per secret. | `bool` | `false` |
| `tags` | Extra tags merged onto all resources. | `map(string)` | `{}` |

## Outputs

| Name | Description |
|---|---|
| `github_token_secret_arn` / `github_token_secret_name` | DevOps GitHub token secret. |
| `pr_reviewer_github_token_secret_arn` / `pr_reviewer_github_token_secret_name` | PR-Reviewer read-only GitHub token secret (distinct from the above). |
| `azure_service_principal_secret_arn` / `azure_service_principal_secret_name` | Azure SP secret. |
| `registry_credentials_secret_arn` / `registry_credentials_secret_name` | Registry credentials secret. |
| `secret_arns` | Map of all 4 ARNs keyed by credential purpose. |
| `secret_names` | Map of all 4 names keyed by credential purpose. |
| `kms_key_arn` / `kms_key_id` | The KMS key used to encrypt all 4 secrets. |
| `standalone_read_policy_arns` | Map of credential purpose -> standalone IAM policy ARN (empty unless `create_standalone_read_policies = true`). |

## Requirements traceability

- **Requirement 11.2** ("ALL credentials ... SHALL be stored in AWS Secrets Manager and injected
  at tool-call time only"): this module provisions the storage side of that requirement — all 4
  named credential types exist as Secrets Manager secrets, never as Terraform-managed real values,
  environment variables, or files on disk. The "injected at tool-call time only" half of the
  requirement is implemented by `backend/src/daf/secrets/credentials.py`'s `CredentialsClient`
  (Task 4.1), which fetches a fresh value from these secrets on every call and never caches one
  across calls.
