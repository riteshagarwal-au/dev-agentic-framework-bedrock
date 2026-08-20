# Implementation Plan: DAF Phase 1 — Foundations & Single-App Validation

## Overview

This plan builds Phase 1 of the Dev Agentic Framework bottom-up: shared infrastructure and data contracts first, then the four control-plane algorithms (Router, Cost/Budget Counter Hook, HITL Approval Broker, Hook Pipeline) that everything else composes, then the Hub/Supervisor and the five persistent spoke agents, then the deterministic CI/CD execution path and PR-Reviewer Agent, then observability and the minimal portal, finishing with end-to-end validation against the Phase 1 Success Criteria (source design §13).

**Confirmed implementation stack:**
- **Python** (boto3, Pydantic, Hypothesis for property-based tests) — Hub/Supervisor, all spoke agent action-group logic, Cost/Budget Counter Hook, HITL Approval Broker, hook pipeline, DynamoDB repositories, Lambda handlers.
- **TypeScript/React** — DAF Portal SPA (design.md §9 / Component list, Overview).
- **Terraform (HCL)** — all IaC: state backend with S3-native locking, GitHub OIDC federation, networking, Bedrock resources, DynamoDB tables (including the dead-letter record table), the Step Functions state machine for HITL gate wait/resume, ECS Fargate target infra.

All tasks below produce code, IaC, or automated tests. Tasks marked `*` are optional test sub-tasks; core implementation tasks are never optional.

## Tasks

- [x] 1. Set up monorepo structure and shared tooling
  - Establish the repo layout (`backend/` Python package, `infra/` Terraform root + modules, `portal/` React/TypeScript app, `.github/workflows/`) referenced by every later task.
  - _Requirements: (project scaffolding, no direct acceptance criterion)_

  - [x] 1.1 Create repository directory structure and root tooling config
    - Create `backend/`, `infra/`, `portal/`, `.github/workflows/` top-level directories with placeholder READMEs describing ownership boundaries.
    - _Requirements: N/A (scaffolding)_

  - [x] 1.2 Set up Python backend package with dependency management and quality tooling
    - Initialize the Python package (pyproject.toml), add `boto3`, `pydantic`, `pytest`, `hypothesis`, linting/formatting config.
    - _Requirements: N/A (scaffolding)_

  - [x] 1.3 Set up Terraform project structure and shared variable/backend conventions
    - Create `infra/` root module layout with per-environment variable files and a placeholder backend config block (populated by Task 2.1).
    - _Requirements: N/A (scaffolding)_

  - [x] 1.4 Set up React/TypeScript portal scaffold
    - Initialize the portal SPA (React + TypeScript, build tooling, test runner), no business logic yet.
    - _Requirements: 12.1 (portal exists as the run-control surface)_

- [x] 2. Terraform bootstrap: remote state backend, OIDC federation, base networking
  - Design ref: design.md "Dependencies" section (S3 state backend, DynamoDB, GitHub Actions/OIDC); Requirements 7.4, 7.8, 11.1.

  - [x] 2.1 Write Terraform module for S3-native remote state backend
    - KMS-encrypted, versioned S3 bucket for Terraform state, `use_lockfile = true` native locking, one backend per environment/target.
    - _Requirements: 7.4_

  - [x] 2.2 Write Terraform module for GitHub OIDC federation IAM role
    - OIDC identity provider + IAM role trust policy scoped to the specific repo/branch/workflow, permissions limited to ECR push, `terraform apply` on the DAF state backend, and ECS service update.
    - _Requirements: 7.8_

  - [x] 2.3 Write Terraform module for baseline VPC/networking
    - VPC, private/public subnets, and routing needed to host ECS Fargate and Lambda-backed hooks in Phase 1's single-account, single-region topology.
    - _Requirements: (infra prerequisite for Requirement 7.5, 12.1)_

  - [x] 2.4 Write Terraform module for the HITL gate Step Functions state machine
    - State machine implementing the "wait for task token" pattern (design.md Component 4): a single state that starts execution and pauses holding a task token, parameterized by gate type/runId/ticketId, with IAM permissions scoped to `states:SendTaskSuccess`/`states:SendTaskFailure` for the HITL Broker's role.
    - _Requirements: 5.2_

  - [ ]* 2.5 Write validation tests for bootstrap Terraform modules
    - `terraform validate`/`fmt`, `tflint`, and `checkov`/`tfsec` checks wired as a repeatable script/CI job for the modules in 2.1–2.4.
    - _Requirements: 7.2 (deterministic checks pattern applied to the bootstrap modules themselves)_

- [x] 3. Bedrock enablement: Guardrails, Knowledge Base (S3 Vectors), AgentCore Memory
  - Design ref: design.md Component list "Knowledge & Memory — Phase 1"; Dependencies section.

  - [x] 3.1 Write Terraform module for Bedrock Guardrails configuration
    - Guardrail resource with PII redaction, prompt-injection defense, and denied-topics configuration, applied to every agent's model calls.
    - _Requirements: 9.3_

  - [x] 3.2 Write Terraform module for Bedrock Knowledge Base on S3 + S3 Vectors backend
    - KB resource backed by an S3 data source and the S3 Vectors vector store (Phase 1 backend per design.md §6.1.1).
    - _Requirements: 9.1_

  - [x] 3.3 Write Terraform module for AgentCore Memory configuration
    - Short-term (per-run) and long-term memory store configuration used by the post-invocation summarize-and-evict step.
    - _Requirements: 9.4_

  - [x] 3.4 Write Terraform module for per-agent least-privilege IAM roles
    - One distinct IAM role per agent (Supervisor, Discovery, DevOps, Security, Modernization, Portfolio Assessment, PR-Reviewer); Supervisor role explicitly excludes migration-action permissions.
    - _Requirements: 2.3, 11.1_

  - [ ]* 3.5 Write validation tests for Bedrock Terraform modules
    - `terraform validate`/`tflint`/`checkov` checks for the modules in 3.1–3.4, plus an assertion that no two agent roles share a policy document.
    - _Requirements: 11.1_

- [x] 4. MCP connector wiring, secrets management, and tool allowlists
  - Design ref: design.md "Security Considerations"; Algorithm 4 pre-invocation step "enforceToolAllowlist".

  - [x] 4.1 Implement Secrets Manager credential retrieval helper (Python)
    - A helper module that fetches GitHub token, Azure service-principal, and registry credentials from Secrets Manager at call time only, never returning them in a form that gets logged.
    - _Requirements: 11.2, 11.3_

  - [x] 4.2 Implement per-agent MCP tool allowlist configuration and enforcement helper
    - Declarative allowlist config per agent (design.md Component 5 table: GitHub MCP, Terraform MCP, AWS API/CLI MCP, Azure MCP, S3/KB MCP, Filesystem, AWS Docs MCP) and an `enforce_tool_allowlist(agent, tool_name)` function used by the pre-invocation hook.
    - _Requirements: 11.4, 11.5_

  - [x] 4.3 Write Terraform for Secrets Manager secret resources and access policies
    - Secret resources for GitHub token, Azure SP, registry credentials, with IAM policies granting read access only to the roles from Task 3.4 that need each secret.
    - _Requirements: 11.2_

  - [ ]* 4.4 Write unit tests for secrets handling and allowlist enforcement
    - Assert the credential helper never returns/serializes secrets into log-shaped output, and that `enforce_tool_allowlist` blocks a tool call outside an agent's configured allowlist regardless of any instruction text passed in.
    - _Requirements: 11.3, 11.4_

- [x] 5. DynamoDB persistence layer for run state
  - Design ref: design.md Data Models "Model 1: RunConfig/RunState", "Model 2: RunCounters", "Model 3: HitlGateTicket"; Algorithm 4 postconditions; Requirement 8.3 (dead-letter persistence).

  - [x] 5.1 Define DynamoDB table schemas for RunState, RunCounters, GateTicket, and DeadLetterRecord (Terraform)
    - Table definitions keyed as: RunState by `runId` (+ `currentStepIndex` attribute), RunCounters by `runId`, GateTicket by `ticketId` with a `runId` GSI, DeadLetterRecord by a generated `deadLetterId` with a `runId` GSI.
    - _Requirements: 8.1, 8.3_

  - [x] 5.2 Implement Python repository layer for RunState persistence
    - `RunStateRepository` with idempotent per-step-boundary writes keyed by `runId + stepIndex`, and a read path that reconstructs `taskGraph`/`currentStepIndex`/`status`.
    - _Requirements: 8.1, 8.5_

  - [x] 5.3 Implement Python repository layer for RunCounters persistence
    - `RunCountersRepository` with an atomic increment operation (DynamoDB conditional/atomic update) for `totalTokensIn`, `totalTokensOut`, `totalWallClockMs`, `totalSteps`, `opusInvocations`, `estimatedCostUsd`.
    - _Requirements: 4.5, 4.6_

  - [x] 5.4 Implement Python repository layer for GateTicket persistence
    - `GateTicketRepository` with create/read/update, enforcing that a ticket is persisted before any notification is sent.
    - _Requirements: 5.3, 5.7_

  - [x] 5.5 Implement Python repository layer for DeadLetterRecord persistence
    - `DeadLetterRecordRepository` with a create/list-by-run operation, persisting the task envelope reference, error detail, retry count, and trace ID for a failure whose retries were exhausted.
    - _Requirements: 8.3_

  - [x]* 5.6 Write unit tests for repository layer CRUD and idempotent writes
    - Cover RunState step-boundary idempotency, RunCounters atomic increment under concurrent calls, GateTicket create/read, and DeadLetterRecord create/list.
    - _Requirements: 8.1_

  - [x]* 5.7 Write property test for run resumability (Property 8)
    - **Property 8: Run resumability** — generate random sequences of step-completions and halts/resumes; assert `RunState.taskGraph` and `RunCounters` after resume reflect exactly the steps completed before the halt, with no double-counted usage and no re-run of completed steps.
    - **Validates: Requirements 8.1, 8.5**

- [x] 6. Core shared data models and contracts (Python)
  - Design ref: design.md "Data Models" (all four models), Component 5 "Common interface".

  - [x] 6.1 Implement Pydantic models for TaskEnvelope, ArtifactRef, SpokeResult, RunConfig, RunState, BudgetCeiling, RunCounters, GateTicket, and shared enums
    - Includes the `ArtifactRef`-only rule (no inlined artifacts in `TaskEnvelope.inputs`), `HitlGateType` (7 values), `ModelTier`, `RunStatus`.
    - _Requirements: 2.2, 4.4 (data model portion)_

  - [x] 6.2 Implement SpokeAgent interface/base class and output-schema validation utility
    - Abstract `SpokeAgent.execute(envelope) -> SpokeResult` base class plus a `validate_output_schema(result, schema)` utility used by every agent and the hook pipeline.
    - _Requirements: 2.1_

  - [x]* 6.3 Write unit tests for data model validation rules
    - Assert `ArtifactRef`-only enforcement on `TaskEnvelope.inputs`, enum completeness for `HitlGateType`, and rejection of malformed `RunConfig`/`BudgetCeiling`.
    - _Requirements: 2.2_

- [x] 7. Deterministic Router with agentic escalation (Algorithm 1)
  - Design ref: design.md "Algorithm 1: Deterministic Router + Agentic Escalation".

  - [x] 7.1 Implement task→model policy table and resolveModel routing logic
    - `TASK_MODEL_POLICY` table covering every `TaskType`; `resolveModel(taskType, attemptState)` per Algorithm 1 including the raise-on-missing-entry behavior and monotonic escalation (Haiku→Sonnet→Opus, gated via `checkOpusGate`).
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [x] 7.2 Implement recordOutcome and escalation logging
    - `Router.recordOutcome(taskId, tier, confidence, succeeded)` and a structured escalation log entry (`taskId`, `fromTier`, `toTier`, `reason`) emitted whenever `resolveModel` returns a higher tier than the previous call for that task.
    - _Requirements: 3.8_

  - [x]* 7.3 Write unit tests for router policy lookup and escalation ladder edge cases
    - Cover: missing policy entry raises; attempt 1 never escalates; Sonnet retries below `MAX_SONNET_RETRIES` stay at Sonnet; Opus-gate `DENIED` raises `RunHalt`; already-at-Opus-and-failing raises `RunHalt`.
    - _Requirements: 3.2, 3.4, 3.5, 3.6_

  - [x]* 7.4 Write property test for escalation monotonic and bounded (Property 4)
    - **Property 4: Escalation is monotonic and bounded** — generate random attempt-state sequences for a single task; assert the returned tier sequence is non-decreasing (Haiku ≤ Sonnet ≤ Opus) and that the sequence terminates (via `RunHalt`) within `MAX_SONNET_RETRIES + maxOpusInvocations` attempts.
    - **Validates: Requirements 3.3, 3.6, 3.7**

- [x] 8. Cost/Budget Counter Hook (Algorithm 2)
  - Design ref: design.md "Algorithm 2: Cost/Budget Counter Hook — threshold checks".

  - [x] 8.1 Implement preCheck threshold evaluation logic
    - `preCheck(runId, estimatedTokens)`: kill-switch short-circuit, then token/cost/wall-clock/step ceiling checks against `RunCounters`/`BudgetCeiling`, read-only (no state mutation).
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 8.2 Implement recordUsage with idempotency key handling
    - `recordUsage(runId, agentId, tokensIn, tokensOut, wallClockMs)` with an idempotency-key guard so duplicate calls for the same invocation are a no-op, backed by the atomic increment from Task 5.3.
    - _Requirements: 4.5, 4.6_

  - [x] 8.3 Implement checkOpusGate logic as a pure budget cap
    - `checkOpusGate(runId)`: `ALLOWED` if and only if `opusInvocations < maxOpusInvocations`, `DENIED` otherwise — a pure budget-cap check with no HITL-override path in Phase 1 (deferred to Phase 2, where a dedicated Opus/cost-escalation gate type may be introduced; Phase 1 does not reuse `DESTRUCTIVE_ACTION` or any other gate as a proxy).
    - _Requirements: 4.7, 4.8_

  - [x] 8.4 Implement detectRepeatedNoProgress and circuit breaker trigger
    - Bounded-lookback (`NO_PROGRESS_LOOKBACK`) detector over the last N recorded steps for a run; on trip, calls `triggerCircuitBreaker(runId, agentId, reason)`.
    - _Requirements: 4.10_

  - [x] 8.5 Implement detectConsecutiveFailures and wire both circuit-breaker triggers into recordUsage
    - Bounded per-agent consecutive-`FAILED`-count detector for `(runId, agentId)`, reset to zero on any non-`FAILED` result; on reaching `MAX_CONSECUTIVE_FAILURES`, calls `triggerCircuitBreaker(runId, agentId, reason)`. Wire both this detector and `detectRepeatedNoProgress` (Task 8.4) into `recordUsage` (Task 8.2) as two independent triggers feeding the same circuit-breaker mechanism.
    - _Requirements: 4.12_

  - [x] 8.6 Implement global kill switch read/write
    - `isKillSwitchActive(runId)` / `activateKillSwitch(runId)` backed by a `run-state` flag every hook checks pre-invocation; once active, no new spoke invocation for the run starts.
    - _Requirements: 4.1, 4.11_

  - [x]* 8.7 Write property test for budget caps never exceeded (Property 2)
    - **Property 2: Budget caps are never exceeded** — generate random sequences of `recordUsage` calls; assert `totalTokensIn + totalTokensOut ≤ maxTotalTokens` and the equivalent cost/wall-clock/step invariants hold after every call, not just at the end.
    - **Validates: Requirements 4.2, 4.3**

  - [x]* 8.8 Write property test for Opus never invoked outside its gate (Property 3)
    - **Property 3: Opus is never invoked outside its gate** — generate random sequences of `checkOpusGate` calls (pure budget-cap rule: `ALLOWED` iff `opusInvocations < maxOpusInvocations`) and simulated Opus invocations; assert `opusInvocations` only increments immediately after a prior `checkOpusGate` call returned `ALLOWED`.
    - **Validates: Requirements 4.7, 4.8, 3.4, 3.5**

  - [x]* 8.9 Write unit tests for consecutive-failures circuit breaker
    - Assert the counter resets on any non-`FAILED` result, trips exactly at `MAX_CONSECUTIVE_FAILURES`, and trips independently of `detectRepeatedNoProgress` (Task 8.4).
    - _Requirements: 4.12_

  - [x]* 8.10 Write property test for kill switch effectiveness (Property 6)
    - **Property 6: Kill switch is effective** — once `activateKillSwitch(runId)` is called, assert every subsequent `preCheck` for that `runId` returns `HALT` and no simulated new spoke invocation is allowed to start, across randomly generated subsequent call sequences.
    - **Validates: Requirements 4.1, 4.11**

  - [x]* 8.11 Write property test for idempotent usage recording (Property 7)
    - **Property 7: Idempotent usage recording** — generate arbitrary duplicate-call sequences with the same idempotency key; assert `RunCounters` after N duplicate calls equals `RunCounters` after exactly 1 call.
    - **Validates: Requirements 4.6**

- [x] 9. HITL Approval Broker (Algorithm 3)
  - Design ref: design.md "Algorithm 3: HITL Gate state machine", "Component 4: HITL Approval Broker" (Step Functions wait/resume mechanism).

  - [x] 9.1 Implement raiseGate: start Step Functions execution and persist ticket
    - `raiseGate(gate, runId, context)`: create `PENDING` ticket, call `StepFunctions.startExecutionAndWaitForTaskToken(gate, runId, ticketId)` against the state machine from Task 2.4 and store the returned task token on `ticket.stepFunctionsTaskToken`, persist the ticket before notifying, set `RunState.status = AWAITING_HITL`, write `hitl_gate_raised` audit event. `raiseGate` returns once the ticket is persisted — it does not itself block; the wait is held durably by Step Functions.
    - _Requirements: 5.2, 5.3_

  - [x] 9.2 Implement decide: resume the held Step Functions execution with PENDING guard
    - `decide(ticketId, decision, approver)`: reject if ticket is not `PENDING`; on `APPROVED` persist + audit + set `RunState.status = RUNNING` + call `StepFunctions.sendTaskSuccess(ticket.stepFunctionsTaskToken, result: APPROVED)` to resume the blocked task; on `REJECTED` persist + audit + set `RunState.status = HALTED` + call `StepFunctions.sendTaskFailure(ticket.stepFunctionsTaskToken, reason)` without resuming or working around it.
    - _Requirements: 5.4, 5.5, 5.6, 5.7_

  - [x] 9.3 Implement getPendingGates query
    - `getPendingGates(runId)` returning all `PENDING` tickets for a run, used by the portal.
    - _Requirements: 12.3_

  - [x]* 9.4 Write unit tests for gate state machine transitions
    - Cover all valid transitions (`PENDING→APPROVED`, `PENDING→REJECTED`) and invalid transitions (deciding an already-decided ticket must raise, not silently succeed); mock the Step Functions client to assert `sendTaskSuccess`/`sendTaskFailure` are called against the correct held task token.
    - _Requirements: 5.4_

  - [x]* 9.5 Write property test for no unapproved state-changing action (Property 1)
    - **Property 1: No unapproved state-changing action** — for randomly generated sequences of gate raises/decisions and simulated gated actions, assert no gated action is recorded as taken unless a `GateTicket` with matching `gateType` and `status = APPROVED` exists for that run with a `decidedAt` timestamp before the action's timestamp.
    - **Validates: Requirements 5.1, 5.2, 5.5, 5.6**

- [x] 10. Pre/Post agent-invocation hook pipeline (Algorithm 4)
  - Design ref: design.md "Algorithm 4: Pre/Post Agent-Invocation Hook Pipeline", "Sequence Diagrams" (hook pipeline diagram).

  - [x] 10.1 Implement pre-invocation stage
    - `attachGuardrails`, `attachCachedSystemPrompt`, `enforceToolAllowlist` (Task 4.2), `CostBudgetHook.preCheck` (Task 8.1) with `HALT`→fail-fast, and blocking-gate lookup/raise (Task 9.1) — the raise starts a Step Functions "wait for task token" execution and returns immediately; the pipeline invocation ends there and is re-entered only when `decide` (Task 9.2) resumes the held token, not via a busy-loop wait.
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 10.2 Implement invocation stage wiring to Bedrock Agents runtime
    - `agent.execute(envelope, tier)` call wiring using the tier resolved by `Router.resolveModel` (Task 7.1), capturing elapsed time and raw token usage from the Bedrock response.
    - _Requirements: 2.1_

  - [x] 10.3 Implement post-invocation stage
    - Output schema validation (Task 6.2) with fail-on-invalid, `CostBudgetHook.recordUsage` (Task 8.2), exactly-one audit event write, `Memory.summarizeAndEvict` call, and the bounded low-confidence retry through the Router's escalation ladder.
    - _Requirements: 6.5, 6.6, 6.7, 6.8, 6.9, 9.4_

  - [x] 10.4 Implement exponential-backoff retry with dead-letter persistence for transient errors
    - Wrap tool/model calls in the pipeline with exponential-backoff retry up to a configured maximum retry count for transient errors (throttling, transient tool/model failures); on retry exhaustion, persist a `DeadLetterRecord` (Task 5.5) with the task envelope reference, error detail, retry count, and trace ID, and raise a HITL alert referencing the dead-letter record.
    - _Requirements: 8.3_

  - [x]* 10.5 Write unit tests for hook pipeline ordering and failure short-circuiting
    - Assert `agent.execute` is never called before Guardrails/allowlist/budget/HITL checks pass, and that a budget `HALT` or gate `REJECTED` short-circuits with a `FAILED` result and no model call.
    - _Requirements: 6.2, 6.3, 6.4_

  - [x]* 10.6 Write unit tests for backoff retry and dead-letter persistence
    - Assert retries follow exponential backoff up to the configured max, and that exhausting retries produces exactly one `DeadLetterRecord` plus one HITL alert referencing it.
    - _Requirements: 8.3_

  - [x]* 10.7 Write property test for exactly-once audit per invocation (Property 5)
    - **Property 5: Every invocation is audited exactly once** — generate random sequences of successful and failing `invokeSpoke` calls; assert each completed call produces exactly one `agent_invocation_complete` audit event with a matching trace ID.
    - **Validates: Requirements 10.2, 6.7**

- [x] 11. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Hub/Supervisor orchestration
  - Design ref: design.md "Component 1: Hub / Supervisor".

  - [x] 12.1 Implement Supervisor.startRun task-graph decomposition
    - Decompose an incoming `RunConfig` into a task graph across the 5 core agents without calling any MCP tool or cloud API directly; persist initial `RunState` (Task 5.2).
    - _Requirements: 1.1_

  - [x] 12.2 Implement Supervisor.routeTask brokering through Router and hook pipeline
    - `routeTask(task, runId)`: invoke the Router (Task 7.1) before dispatch, call `invokeSpoke` (Task 10.x), and broker any agent-to-agent handoff itself (star topology — no direct spoke-to-spoke calls).
    - _Requirements: 1.2, 1.3_

  - [x] 12.3 Implement Supervisor.getRunStatus and killRun
    - `getRunStatus(runId)` returning one of the six defined statuses reflecting true task-graph state; `killRun(runId, reason)` stopping further routing and draining in-flight invocations.
    - _Requirements: 1.4, 1.5_

  - [x]* 12.4 Write unit tests for Supervisor orchestration and star-topology brokering
    - Assert `startRun` never calls an MCP tool/cloud API directly, and that a simulated handoff always routes through the Supervisor rather than agent-to-agent.
    - _Requirements: 1.1, 1.3_

  - [x]* 12.5 Write integration tests for startRun → routeTask → HITL → resume flow
    - End-to-end (stubbed agents) test exercising `startRun`, a routed task that hits a HITL gate, a `decide(APPROVED)` call, and confirmation the blocked task resumes correctly.
    - _Requirements: 1.1, 1.2, 5.5_

- [x] 13. Persistent core agents: Discovery, DevOps, Security, Modernization, Portfolio Assessment
  - Design ref: design.md "Component 5: Persistent Core Agents" table.

  - [x] 13.1 Implement Discovery Agent action group
    - Implements `SpokeAgent.execute` for inventory collection (Haiku-tier tasks) and reasoning (Sonnet-tier tasks) over Azure MCP + Filesystem MCP inputs, per the task→model default split.
    - _Requirements: 2.1, 2.4_

  - [x] 13.2 Implement DevOps Agent action group
    - Implements `SpokeAgent.execute` for Terraform + GitHub Actions workflow generation; opens a pull request via the GitHub MCP connector and never applies changes directly.
    - _Requirements: 2.1, 2.5_

  - [x] 13.3 Implement Security Agent action group
    - Implements `SpokeAgent.execute` returning a pass result or a list of findings for a migration/Terraform plan; never itself approves or blocks the plan.
    - _Requirements: 2.1, 2.6_

  - [x] 13.4 Implement Modernization Agent action group
    - Implements `SpokeAgent.execute` producing the target-state blueprint and migration plan from Discovery's inventory output, retrieving guidance from both the corporate KB (S3/KB MCP) and AWS Documentation MCP.
    - _Requirements: 2.1_

  - [x] 13.5 Implement Portfolio Assessment Agent action group
    - Implements `SpokeAgent.execute` for complexity/risk/value categorization and pathway recommendation.
    - _Requirements: 2.1_

  - [x] 13.6 Implement KB-vs-AWS-Docs conflict detection and flagging
    - Shared helper (used by Modernization Agent and any other agent retrieving both sources) that compares corporate-KB guidance against AWS Documentation MCP guidance for a retrieval; on conflict, follows the KB guidance, records the conflict (KB guidance, AWS Docs guidance, KB-following decision) in `SpokeResult.notes`, and causes the pipeline to write a dedicated `kb_conflict_flagged` audit event correlated to the run's trace ID.
    - _Requirements: 9.2_

  - [x] 13.7 Write Terraform for Bedrock Agent resources per agent
    - Bedrock Agent resource + action group wiring for each of the 5 core agents, attached to the IAM roles from Task 3.4 and the Guardrails from Task 3.1.
    - _Requirements: 2.3_

  - [x]* 13.8 Write unit tests for each core agent's output schema conformance
    - Assert each agent's `SpokeResult.output`/`confidence`/`tokensUsed`/`status`/`notes` conforms to its declared output schema for representative inputs.
    - _Requirements: 2.1_

  - [x]* 13.9 Write unit tests for DevOps Agent PR-open-only behavior
    - Assert the DevOps Agent's generated actions only ever call the GitHub MCP "open PR" operation, never an apply/merge operation.
    - _Requirements: 2.5_

  - [x]* 13.10 Write unit tests for KB-vs-AWS-Docs conflict flagging
    - Assert a simulated conflicting retrieval follows the KB guidance, populates `SpokeResult.notes` with both guidance sources and the decision, and produces exactly one `kb_conflict_flagged` audit event.
    - _Requirements: 9.2_

- [x] 14. PR-Reviewer Agent and deterministic CI/CD execution path
  - Design ref: design.md "Component 6: Deterministic CI/CD path"; "Sequence Diagrams" main flow.

  - [x] 14.1 Implement PR-Reviewer Agent
    - Implements `SpokeAgent.execute` producing a risk score, plain-English diff summary, KB conformance notes, focus list, and cost delta, posted as a PR comment via a read-only GitHub MCP connection; never merges or approves.
    - _Requirements: 7.3_

  - [x] 14.2 Write GitHub Actions workflow for deterministic PR checks
    - Workflow running `terraform fmt`/`validate`, `tflint`, `checkov`/`tfsec`, and posting `terraform plan` output as a PR comment, triggered on any infrastructure-affecting PR.
    - _Requirements: 7.2_

  - [x] 14.3 Write Terraform for target ECS Fargate infrastructure
    - ECS Fargate cluster/service/task-definition module for the synthetic application deploy target, built on the networking module from Task 2.3.
    - **Repo scope note:** this is infrastructure for the *synthetic/target application*, which lives in its own separate repo (DevOps Agent opens PRs into that repo via GitHub MCP, per `daf/agents/devops.py`) — it does not belong inside the DAF repo's own `infra/`. An earlier pass mistakenly added `infra/modules/ecs-fargate-target/` here; it has been removed. Re-implement this module in the target app's repo when that repo exists.
    - _Requirements: (deploy target for Requirement 7.5)_

  - [x] 14.4 Write GitHub Actions workflow for terraform plan/apply gated by HITL
    - Workflow that runs `terraform apply` against the S3-backed remote state (Task 2.1) using OIDC auth (Task 2.2) only after the PR-merge and infra-apply HITL gates are approved.
    - **Repo scope note:** same as 14.3 — this workflow runs in the *target app's* repo (opened/maintained there by DevOps Agent), not in DAF's own `.github/workflows/`. An earlier pass mistakenly added `terraform-apply.yml` here; it has been removed.
    - _Requirements: 7.4, 7.8_

  - [x] 14.5 Write GitHub Actions workflow for container build/deploy to ECS Fargate
    - Workflow that builds/pushes the container image and deploys to the ECS Fargate target from Task 14.3, gated on the cloud-deploy HITL approval.
    - **Repo scope note:** same as 14.3/14.4 — belongs in the target app's repo. `container-deploy.yml` was removed from this repo for the same reason.
    - _Requirements: 7.5_

  - [x] 14.6 Implement scripted (non-LLM) smoke-test CI step and result reporting
    - Deterministic script performing a health-endpoint check and a basic functional check post-deploy; reports pass/fail back to the Hub's audit log; on failure, halts and raises a HITL alert instead of attempting remediation.
    - _Requirements: 7.6, 7.7_

  - [x] 14.7 Implement HITL-gated compensation action path
    - `compensate(runId, sequenceRef)` action (e.g. `terraform destroy` of the just-applied module) available for a halted state-changing sequence; the action itself calls `HitlBroker.raiseGate(DESTRUCTIVE_ACTION, runId, context)` (Task 9.1) and does not execute until that gate's ticket is `APPROVED`.
    - _Requirements: 8.4_

  - [x]* 14.8 Write unit tests for PR-Reviewer Agent advisory-only behavior
    - Assert the PR-Reviewer Agent never calls a GitHub MCP merge/approve operation and treats the diff content as untrusted data.
    - _Requirements: 7.3, 9.5_

  - [x]* 14.9 Write unit tests for smoke-test script pass/fail reporting
    - Assert a failing health/functional check halts the pipeline and produces the expected audit-log report without attempting a retry/remediation.
    - _Requirements: 7.6, 7.7_

  - [x]* 14.10 Write unit tests for compensation action HITL gating
    - Assert `compensate()` never executes the underlying destructive action before its `DESTRUCTIVE_ACTION` gate ticket is `APPROVED`, and that a `REJECTED` decision leaves the compensation unexecuted.
    - _Requirements: 8.4_

- [x] 15. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 16. Observability and audit trail
  - Design ref: design.md "Performance Considerations"; source design §12.2 (carried into design.md Dependencies).

  - [x] 16.1 Implement OpenTelemetry instrumentation for Supervisor, hook pipeline, and core agents
    - Spans correlated by a single per-run trace ID, propagated into every `TaskEnvelope` and exported to CloudWatch/X-Ray.
    - _Requirements: 10.1_

  - [x] 16.2 Implement structured audit event writer with trace ID correlation
    - JSON structured audit log writer used by the hook pipeline (Task 10.3) and HITL broker (Task 9.1/9.2), guaranteeing exactly-one-event semantics per invocation/decision.
    - _Requirements: 10.2, 10.3, 10.4_

  - [x] 16.3 Implement per-agent metrics recording
    - Per-invocation metrics: latency, token/cost usage, escalation occurrences, tool error rate, recorded alongside the audit event.
    - _Requirements: 10.5_

  - [x]* 16.4 Write unit tests for trace ID propagation
    - Assert a trace ID generated at `startRun` is present in every task envelope and audit event produced during a simulated run.
    - _Requirements: 10.1_

  - [x]* 16.5 Write integration test reconstructing a full run from the audit log alone
    - Run a stubbed end-to-end scenario, then reconstruct the full action sequence purely from audit events and assert it matches the actual sequence taken.
    - _Requirements: 10.4_

- [x] 17. Minimal DAF Portal (React/TypeScript)
  - Design ref: design.md Overview ("Minimal portal"), Phase 1 scope boundary table; requirements.md Requirement 12.

  - [x] 17.1 Implement API Gateway + Lambda backend endpoints for portal (Python)
    - Endpoints for start-run, get-run-status, list-pending-gates, and decide-gate, wired to the Supervisor (Task 12.x) and HITL Broker (Task 9.x), authenticated via Cognito.
    - _Requirements: 12.1, 12.2, 12.4_

  - [x] 17.2 Implement Cognito-authenticated API client and route guards (TypeScript)
    - Portal API client enforcing an authenticated session for every run-control call; unauthenticated requests never reach a run-control action.
    - _Requirements: 12.4_

  - [x] 17.3 Implement run kickoff and live run-status monitoring views
    - Views to start a new run for the synthetic app and display live status including current task-graph step and `AWAITING_HITL` state.
    - _Requirements: 12.1, 12.2_

  - [x] 17.4 Implement HITL approval ticket list and decision view
    - View surfacing pending gate tickets with artifact references/summary context, and an approve/reject action calling the decide-gate endpoint.
    - _Requirements: 12.3_

  - [x]* 17.5 Write unit tests for portal API backend endpoints
    - Assert unauthenticated requests are rejected and that decide-gate calls are correctly forwarded to the HITL Broker.
    - _Requirements: 12.4_

  - [x]* 17.6 Write component tests for portal kickoff/monitor/approval views
    - Cover rendering of run status transitions and the approval ticket decision flow.
    - _Requirements: 12.2, 12.3_

- [x] 18. Phase 1 end-to-end validation against success criteria
  - Design ref: design.md "Testing Strategy" (integration testing approach); source design §13 "Phase 1 Success Criteria".

  - [x] 18.1 Implement integration test for full synthetic-app migration flow through all 7 HITL gates
    - Stubbed Azure source + disposable AWS target dry run exercising Discovery → Modernization → plan-finalize gate → Security → DevOps → PR → PR-merge gate → infra-apply gate → cloud-deploy gate, per the main-flow sequence diagram.
    - _Requirements: 5.1, 7.1 through 7.6_

  - [x] 18.2 Implement deliberate-trigger tests for kill switch, hard caps, and circuit breaker
    - Deliberately trip each Phase 1 safety mechanism at least once in a test run and assert halt/alert behavior, per source design §13 "Safety mechanisms exercised".
    - _Requirements: 4.1, 4.2, 4.10, 4.11_

  - [x] 18.3 Implement model-tier call-mix logging assertion against the 70/28/2 target
    - Test harness that runs a representative task mix through the Router and asserts the logged Haiku/Sonnet/Opus call-volume split is captured for baseline comparison.
    - _Requirements: 3.8_

  - [x]* 18.4 Write integration test for audit-log-only reconstruction of an end-to-end run
    - Extend Task 16.5's reconstruction test to the full migration flow from Task 18.1, confirming 100% of agent actions and HITL decisions are traceable from the audit log alone.
    - _Requirements: 10.4_

- [x] 19. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP; core implementation tasks (unmarked) are never optional.
- Property-based test tasks (Hypothesis, Python) map 1:1 to the 8 Correctness Properties in design.md and are placed immediately after the implementation they validate.
- No TypeScript logic in the Phase 1 portal carries its own correctness-property obligations (it is a thin authenticated CRUD/monitoring surface over the backend APIs), so no `fast-check` property tests are included; portal testing uses standard component/unit tests.
- Terraform "apply" is intentionally out of scope for this task list — tasks produce and statically validate (`validate`/`plan`/`tflint`/`checkov`) IaC; actual applies happen through the HITL-gated CI/CD path built in Task 14, not as a standalone coding-agent action.
- Checkpoints (Tasks 11, 15, 19) are natural points to pause and confirm direction before moving into the next major subsystem.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4", "2.1", "2.2", "2.3", "2.4", "3.1", "3.2", "3.3", "3.4", "4.1", "4.2", "4.3", "5.1", "6.1", "14.2"] },
    { "id": 1, "tasks": ["2.5", "3.5", "4.4", "5.2", "5.3", "5.4", "5.5", "6.2", "7.1", "14.3", "13.7"] },
    { "id": 2, "tasks": ["5.6", "5.7", "6.3", "7.2", "8.1", "9.1", "14.4", "13.1", "13.2", "13.3", "13.4", "13.5", "14.1"] },
    { "id": 3, "tasks": ["7.3", "7.4", "8.2", "9.2", "14.5", "13.8", "13.9", "14.8"] },
    { "id": 4, "tasks": ["8.3", "9.3", "13.6", "14.6", "14.7"] },
    { "id": 5, "tasks": ["8.4", "9.4", "9.5", "13.10", "14.9", "14.10"] },
    { "id": 6, "tasks": ["8.5"] },
    { "id": 7, "tasks": ["8.6"] },
    { "id": 8, "tasks": ["8.7", "8.8", "8.9", "8.10", "8.11"] },
    { "id": 9, "tasks": ["10.1"] },
    { "id": 10, "tasks": ["10.2"] },
    { "id": 11, "tasks": ["10.3", "10.4"] },
    { "id": 12, "tasks": ["10.5", "10.6", "10.7", "12.1"] },
    { "id": 13, "tasks": ["12.2"] },
    { "id": 14, "tasks": ["12.3"] },
    { "id": 15, "tasks": ["12.4", "12.5"] },
    { "id": 16, "tasks": ["16.1", "16.2", "16.3"] },
    { "id": 17, "tasks": ["16.4", "16.5", "17.1"] },
    { "id": 18, "tasks": ["17.2"] },
    { "id": 19, "tasks": ["17.3", "17.4"] },
    { "id": 20, "tasks": ["17.5", "17.6"] },
    { "id": 21, "tasks": ["18.1", "18.2", "18.3"] },
    { "id": 22, "tasks": ["18.4"] }
  ]
}
```
