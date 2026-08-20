# backend/

## Ownership

This directory contains the **Python backend package** for the Dev Agentic Framework (DAF), Phase 1.

Owned by: Backend/Agent Platform engineering.

## Scope

This is where all Python code lives, including:

- **Hub/Supervisor orchestration** — task-graph decomposition, routing brokerage, run status/kill.
- **Deterministic Router + Agentic Escalation** (Algorithm 1) — task→model policy table, escalation ladder.
- **Cost/Budget Counter Hook** (Algorithm 2) — threshold checks, kill switch, Opus gate, circuit breakers.
- **HITL Approval Broker** (Algorithm 3) — gate ticket state machine, Step Functions wait/resume integration.
- **Pre/Post Agent-Invocation Hook Pipeline** (Algorithm 4) — Guardrails attachment, tool allowlist
  enforcement, schema validation, audit logging, retry/dead-letter handling.
- **Persistent core spoke agents** — Discovery, DevOps, Security, Modernization, Portfolio Assessment,
  and the on-demand PR-Reviewer agent action-group logic.
- **Shared data models/contracts** — Pydantic models for `TaskEnvelope`, `ArtifactRef`, `SpokeResult`,
  `RunConfig`, `RunState`, `BudgetCeiling`, `RunCounters`, `GateTicket`, and shared enums.
- **DynamoDB repository layer** — `RunStateRepository`, `RunCountersRepository`, `GateTicketRepository`,
  `DeadLetterRecordRepository`.
- **Lambda handlers** — API backend endpoints consumed by the portal (`portal/`).
- **Secrets/credential helpers and MCP tool allowlist enforcement**.
- **Observability** — OpenTelemetry instrumentation, structured audit event writer, per-agent metrics.

## Out of scope

- Terraform/IaC definitions (see `infra/`).
- Portal UI code (see `portal/`).
- CI/CD workflow definitions (see `.github/workflows/`).

See [`../.kiro/specs/daf-phase1-foundations/design.md`](../.kiro/specs/daf-phase1-foundations/design.md)
for the full component design.
