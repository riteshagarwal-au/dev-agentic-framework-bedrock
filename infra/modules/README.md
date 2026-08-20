# infra/modules/

## Purpose

This directory holds reusable Terraform submodules consumed by the `infra/` root module. Each
submodule is scoped to one logical piece of the DAF Phase 1 infrastructure and is wired into
`infra/main.tf` as it's built out.

Submodules are added by:

- **Task 2.1** — `state-backend/`: KMS-encrypted, versioned S3 bucket for Terraform state with
  S3-native locking (`use_lockfile = true`).
- **Task 2.2** — `github-oidc/`: GitHub OIDC identity provider + IAM role trust policy scoped to
  the repo/branch/workflow.
- **Task 2.3** — `networking/`: baseline VPC, subnets, and routing for ECS Fargate and
  Lambda-backed hooks.
- **Task 2.4** — `hitl-gate-state-machine/`: the "wait for task token" Step Functions state
  machine used by the HITL Approval Broker.
- **Task 3.1–3.4** — `bedrock-guardrails/`, `bedrock-knowledge-base/`, `bedrock-agentcore-memory/`,
  `agent-iam-roles/`: Bedrock Guardrails, Knowledge Base (S3 + S3 Vectors), AgentCore Memory, and
  per-agent least-privilege IAM roles.
- **Task 4.3** — `secrets/`: Secrets Manager secret resources and access policies (GitHub token,
  PR-Reviewer GitHub token, Azure SP, registry credentials).
- **Task 5.1** — `dynamodb-tables/`: RunState, RunCounters, GateTicket, DeadLetterRecord tables.
- **Task 13.7** — Bedrock Agent + action-group resources per core agent.
- **Task 14.3** — `ecs-fargate-target/`: cluster/service/task-definition for the synthetic app
  deploy target.

## Convention

Each submodule should:

- Live in its own subdirectory (`infra/modules/<name>/`) with its own `main.tf`, `variables.tf`,
  `outputs.tf`.
- Take all environment-specific values as input variables — no hardcoded account IDs, regions
  (beyond a sensible default), or resource names.
- Avoid declaring a `provider` or `backend` block (inherited from the root module).
- Be independently `terraform validate`-able given a minimal `variables.tf`-only root for testing.
