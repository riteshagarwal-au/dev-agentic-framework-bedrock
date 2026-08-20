# agent-iam-roles

Provisions one distinct, least-privilege IAM role per DAF Phase 1 agent — Supervisor, Discovery,
DevOps, Security, Modernization, Portfolio Assessment, and PR-Reviewer — per Requirements 2.3 and
11.1:

> **Requirement 2.3**: "EACH core agent SHALL run under its own dedicated least-privilege IAM
> role, distinct from the Supervisor's role and from every other agent's role."
>
> **Requirement 11.1**: "EACH agent and worker SHALL run under its own least-privilege IAM role;
> no two agents SHALL share a role, and the Supervisor's role SHALL NOT include migration-action
> permissions."

## Design choice: hybrid `for_each` + per-agent policy blocks

The 7 roles share identical *structure*: the trust policy shape, naming convention, tagging, and
the baseline Bedrock model-invoke grant every agent needs. That shared structure is implemented
once as a `for_each`-keyed set of resources (`aws_iam_role.agent`, `data.aws_iam_policy_document.trust`,
`aws_iam_role_policy.bedrock_model_invoke`).

The 7 roles' *permission* sets differ enough in shape — different resource ARNs, different AWS
service action families, and (for the Supervisor) deliberately zero extra permissions — that
forcing them into one generic templated policy document would obscure each agent's distinct
least-privilege scope, and would make "the Supervisor excludes migration-action permissions"
harder to verify by inspection. So each agent's *extra* permissions (beyond the shared Bedrock
baseline) are their own named `data.aws_iam_policy_document` / `aws_iam_role_policy` pair — one
block per agent, in `main.tf`, in the order: supervisor, discovery, devops, security,
modernization, portfolio-assessment, pr-reviewer. This keeps "one distinct policy document per
agent" visible directly in the code, which is what Task 3.5's validation (an assertion that no two
agent roles share a policy document) checks for — this module's structure is what makes that
assertion true, not a mechanism this module implements itself (that's explicitly Task 3.5's job,
not duplicated here).

## Per-agent scoping rationale

| Agent | Extra grant beyond the shared Bedrock model-invoke baseline | Why |
|---|---|---|
| **Supervisor** | **None.** (Optional: `bedrock:InvokeAgent`/`GetAgentAlias` against collaborator agent aliases, only if `supervisor_collaborator_agent_alias_arns` is set.) | Orchestrates only (design.md Component 1) — never calls an MCP tool or cloud API directly (Requirement 1.1). No S3, no Secrets Manager, no Terraform/ECS/IaC-apply-equivalent permission, no destructive action of any kind. This is the concrete IAM expression of Requirement 11.1's exclusion clause: there is no migration-action statement to strip out, because none is ever added. |
| **Discovery** | Read/write on its own `discovery/*` prefix in the artifacts bucket; read on the Azure service-principal secret. | Azure MCP and Filesystem MCP access are not AWS IAM concerns (they're MCP-level tool connections, not AWS API calls) — the only things IAM actually governs for this agent are its own `ArtifactRef` storage and the credential it needs to authenticate the Azure MCP connector. |
| **DevOps** | Read/write on its own `devops/*` prefix in the artifacts bucket; read on the GitHub-PR-open token secret. | The DevOps Agent opens a pull request and never applies directly (Requirement 2.5, 7.1) — `ecs:UpdateService` and Terraform-apply-equivalent state-bucket access belong to the `github-oidc` module's CI/CD role (Task 2.2), a distinct identity GitHub Actions assumes only after the PR-merge and infra-apply HITL gates are approved. This role never gets that grant. |
| **Security** | Read-only KB retrieve; read-only IAM/Config/SecurityHub check APIs (`var.security_readonly_actions`). | The Security Agent returns a pass result or findings and never itself approves/blocks a plan (Requirement 2.6) — every action in `security_readonly_actions` is a `Get`/`List`/`Describe` call; there is no `Put`/`Create`/`Update`/`Delete` action anywhere in this role. |
| **Modernization** | Read-only KB retrieve. | AWS Documentation MCP is an MCP-level tool, not an AWS API — the only AWS IAM concern is corporate-KB retrieval (Task 3.2), used alongside AWS Docs MCP per the KB-vs-AWS-Docs conflict-detection logic (Task 13.6). |
| **Portfolio Assessment** | Read-only KB retrieve. | Its only tool per design.md Component 5 is S3/KB MCP — no other AWS API access is needed. |
| **PR-Reviewer** | Read on a **read-only-scoped** GitHub token secret (a distinct secret ARN from DevOps's). | Advisory-only: posts a PR comment, never merges or approves (Requirement 7.3, 9.5). Deliberately given a different secret ARN (`pr_reviewer_github_token_secret_arn`) than DevOps's PR-open token (`github_token_secret_arn`), so this role's IAM grant can never reach a merge/approve-capable credential even indirectly — enforcing which GitHub credential *scope* each secret actually holds is Task 4.3's job; this module only wires read access to whichever secret ARN each agent is given. |

Every "extra grant" above is gated behind an input variable defaulting to `null`/`[]` — a
statement is only rendered into that agent's policy document when the relevant upstream resource
(artifacts bucket, KB, secret, guardrail) has actually been provisioned. Before those inputs are
wired up, every agent role still exists with the shared Bedrock model-invoke baseline only.

## Trust policy and confused-deputy prevention

Each role trusts only `bedrock.amazonaws.com`, with **both** of AWS's recommended confused-deputy
conditions on the trust policy (see
[Cross-service confused deputy prevention](https://docs.aws.amazon.com/bedrock/latest/userguide/cross-service-confused-deputy-prevention.html)
and [Create a service role for Amazon Bedrock Agents](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-permissions.html),
which explicitly recommends "as a best practice for security purposes, replace the `*` with
specific agent IDs after you have created them"):

- `aws:SourceAccount` = the current account ID (always applied, not overridable).
- `aws:SourceArn` `ArnLike` — defaults to `arn:aws:bedrock:<region>:<account-id>:agent/*`
  (same-account/same-region wildcard) per agent, overridable per-agent via
  `var.agent_source_arn_patterns`.

**Why a wildcard by default, not the specific agent ID:** this module (Task 3.4) is applied
*before* Task 13.7 creates the actual `aws_bedrockagent_agent` resources that assume these roles —
the agent ID doesn't exist yet at this module's first apply, and Task 13.7 itself takes these
roles' ARNs as an input (a circular dependency if this module tried to require the agent ID
up front). Once Task 13.7 creates each agent and its ID is known, tighten
`var.agent_source_arn_patterns[<agent-key>]` to
`["arn:aws:bedrock:<region>:<account-id>:agent/<agent-id>"]` — this is a trust-policy-only update
on that one role (no replacement of the role itself, no downtime for any other role).

## What this module does NOT create

- The Bedrock Agent resources themselves (action groups, model association, guardrail
  attachment) — that's Task 13.7, which consumes this module's `role_arns` output.
- The artifacts S3 bucket, the Knowledge Base, the Bedrock Guardrail, or the Secrets Manager
  secrets — those are Tasks 3.1/3.2/4.3 respectively; this module only takes their ARNs as
  optional input variables and wires read/write IAM statements against them.
- Any validation that "no two agent roles share a policy document" — that assertion is Task 3.5's
  explicit job. This module's per-agent-policy-document structure (see "Design choice" above) is
  what makes that assertion straightforward to write and true by construction, but the check
  itself lives in Task 3.5, not here.

## Usage

```hcl
module "agent_iam_roles" {
  source      = "../../modules/agent-iam-roles"
  environment = var.environment

  guardrail_arn      = module.bedrock_guardrails.guardrail_arn        # Task 3.1
  knowledge_base_arn = module.bedrock_knowledge_base.knowledge_base_arn # Task 3.2

  artifacts_bucket_arn = module.artifacts_bucket.bucket_arn # separate from the TF state bucket

  azure_sp_secret_arn                 = module.secrets.azure_sp_secret_arn                 # Task 4.3
  github_token_secret_arn             = module.secrets.devops_github_token_secret_arn      # Task 4.3
  pr_reviewer_github_token_secret_arn = module.secrets.pr_reviewer_github_token_secret_arn  # Task 4.3
}
```

```hcl
output "agent_role_arns" {
  value = module.agent_iam_roles.role_arns
}
```

### Tightening the trust policy once Task 13.7's agent IDs are known

```hcl
module "agent_iam_roles" {
  source      = "../../modules/agent-iam-roles"
  environment = var.environment

  agent_source_arn_patterns = {
    supervisor            = ["arn:aws:bedrock:ap-southeast-2:123456789012:agent/ABCDEFGHIJ"]
    discovery              = ["arn:aws:bedrock:ap-southeast-2:123456789012:agent/KLMNOPQRST"]
    devops                 = ["arn:aws:bedrock:ap-southeast-2:123456789012:agent/UVWXYZ0123"]
    security               = ["arn:aws:bedrock:ap-southeast-2:123456789012:agent/4567890ABC"]
    modernization          = ["arn:aws:bedrock:ap-southeast-2:123456789012:agent/DEFGHIJKLM"]
    "portfolio-assessment" = ["arn:aws:bedrock:ap-southeast-2:123456789012:agent/NOPQRSTUVW"]
    "pr-reviewer"          = ["arn:aws:bedrock:ap-southeast-2:123456789012:agent/XYZ0123456"]
  }
}
```

## Feeds into Task 13.7

Task 13.7 ("Write Terraform for Bedrock Agent resources per agent") attaches each core agent's
`aws_bedrockagent_agent` resource to the corresponding role from this module's `role_arns` output
(`agent_resource_role_arn = module.agent_iam_roles.role_arns["discovery"]`, etc.) and to the
Guardrail from Task 3.1. Once those agent resources exist, come back and tighten
`var.agent_source_arn_patterns` per the section above.

## Inputs

| Name | Description | Type | Default |
|---|---|---|---|
| `environment` | Environment/target name; namespaces role names/tags. | `string` | n/a (required) |
| `name_prefix` | Prefix for generated role names/tags. | `string` | `"daf-phase1"` |
| `agent_source_arn_patterns` | Per-agent `aws:SourceArn` `ArnLike` override map, keyed by agent key. | `map(list(string))` | `{}` (wildcard per agent) |
| `foundation_model_arns` | Foundation-model ARNs every role may invoke. | `list(string)` | `null` (all models in-region) |
| `inference_profile_arns` | Inference-profile ARNs every role may invoke. | `list(string)` | `null` (all profiles in-account/region) |
| `guardrail_arn` | Guardrail ARN (Task 3.1) every role gets `ApplyGuardrail` on. | `string` | `null` (statement omitted) |
| `knowledge_base_arn` | KB ARN (Task 3.2) Security/Modernization/Portfolio Assessment get `Retrieve` on. | `string` | `null` (statement omitted) |
| `artifacts_bucket_arn` | Artifacts S3 bucket ARN Discovery/DevOps get scoped read/write on. | `string` | `null` (statement omitted) |
| `azure_sp_secret_arn` | Azure SP secret ARN (Task 4.3) Discovery gets read on. | `string` | `null` (statement omitted) |
| `github_token_secret_arn` | GitHub PR-open token secret ARN (Task 4.3) DevOps gets read on. | `string` | `null` (statement omitted) |
| `pr_reviewer_github_token_secret_arn` | Read-only GitHub token secret ARN (Task 4.3) PR-Reviewer gets read on. Must differ from `github_token_secret_arn`. | `string` | `null` (statement omitted) |
| `security_readonly_actions` | Read-only IAM/Config/SecurityHub actions granted to Security. | `list(string)` | 17-action default list |
| `supervisor_collaborator_agent_alias_arns` | Agent-alias ARNs the Supervisor may `InvokeAgent` on (optional, native multi-agent collaboration only). | `list(string)` | `[]` (statement omitted) |
| `tags` | Extra tags merged onto all resources. | `map(string)` | `{}` |

## Outputs

| Name | Description |
|---|---|
| `role_arns` | Map of agent key -> role ARN, for all 7 agent keys. Primary output consumed by Task 13.7. |
| `role_names` | Map of agent key -> role name. |
| `supervisor_role_arn` / `discovery_role_arn` / `devops_role_arn` / `security_role_arn` / `modernization_role_arn` / `portfolio_assessment_role_arn` / `pr_reviewer_role_arn` | Convenience single-value accessors equivalent to indexing `role_arns`. |

## Requirements traceability

- Requirement 2.3: each of the 5 persistent core agents gets its own `aws_iam_role`, distinct from
  the Supervisor's and from every other agent's — enforced structurally by the `for_each` over
  `local.agent_keys` (7 distinct role resources, 7 distinct names).
- Requirement 11.1: no two agents share a role (same structural argument as above, extended to
  the Supervisor and PR-Reviewer); the Supervisor's role carries no migration-action permission —
  verified by inspection of the "Supervisor" section of `main.tf`, which adds nothing beyond the
  shared Bedrock model-invoke baseline and an optional, non-mutating `InvokeAgent` grant.
