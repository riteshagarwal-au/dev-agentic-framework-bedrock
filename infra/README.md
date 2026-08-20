# infra/

## Ownership

This directory contains the **Terraform (HCL) infrastructure-as-code** for the Dev Agentic Framework
(DAF), Phase 1.

Owned by: Cloud/Platform (DevOps) engineering.

## Scope

This is where all Terraform root modules and reusable modules live, including:

- **Remote state backend** — KMS-encrypted, versioned S3 bucket with S3-native state locking
  (`use_lockfile = true`), one backend per environment/target.
- **GitHub OIDC federation** — IAM identity provider + role trust policy scoped to a specific
  repo/branch/workflow, used by GitHub Actions to authenticate to AWS without long-lived keys.
- **Baseline networking** — VPC, subnets, and routing hosting ECS Fargate and Lambda-backed hooks.
- **HITL gate Step Functions state machine** — the "wait for task token" state machine used by the
  HITL Approval Broker (`backend/`) to durably pause/resume gated actions.
- **Bedrock resources** — Guardrails, Knowledge Base (S3 + S3 Vectors backend), AgentCore Memory
  configuration, Bedrock Agent + action-group resources per core agent.
- **Per-agent least-privilege IAM roles** — one distinct role per agent (Supervisor, Discovery,
  DevOps, Security, Modernization, Portfolio Assessment, PR-Reviewer).
- **DynamoDB tables** — RunState, RunCounters, GateTicket, DeadLetterRecord.
- **Secrets Manager resources** — secret definitions and scoped read-access policies.
- **Target ECS Fargate infrastructure** — cluster/service/task-definition module for the synthetic
  application deploy target.

## Out of scope

- Python application/agent logic (see `backend/`).
- Portal UI code (see `portal/`).
- CI/CD workflow definitions that *invoke* this Terraform (see `.github/workflows/`) — this directory
  only contains the IaC itself, not the pipelines that run `plan`/`apply`.

Terraform `apply` is intentionally never run ad hoc from this directory in Phase 1 — applies happen
only through the HITL-gated CI/CD path in `.github/workflows/`.

See [`../.kiro/specs/daf-phase1-foundations/design.md`](../.kiro/specs/daf-phase1-foundations/design.md)
for the full component design.
