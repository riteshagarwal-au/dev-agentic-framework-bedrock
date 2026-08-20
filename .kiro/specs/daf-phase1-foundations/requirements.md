# Requirements Document

## Feature: DAF Phase 1 — Foundations & Single-App Validation

## Introduction

This requirements document is derived from [`design.md`](./design.md), which scopes the Dev Agentic Framework (DAF) down to its Phase 1 buildable increment: a hub-spoke multi-agent system (Supervisor + 5 persistent core agents + 1 on-demand PR-Reviewer agent) that migrates a synthetic application from Azure to ECS Fargate through a deterministic CI/CD path, governed by 7 human-in-the-loop (HITL) gates, a deterministic Cost/Budget Counter Hook with a kill switch, and durable/auditable run state.

Decisions already settled in the source design ([`_dev-analysis/DAF_Solution_Design.md`](../../../_dev-analysis/DAF_Solution_Design.md)) are treated as constraints here, not open requirements to re-derive: deterministic-first execution (no Migration Worker / agentic Testing agent in Phase 1), S3 Vectors as the Phase 1 KB vector backend, S3-native Terraform state locking, GitHub OIDC federation for CI/CD auth, the Cost/Budget Counter Hook as a deterministic (non-agentic) mechanism, and the PR-Reviewer Agent as a Phase 1 advisory-only layer.

Requirements are written in EARS notation (Easy Approach to Requirements Syntax) and grouped by the components/algorithms defined in the design document.

## Glossary

- **HITL (Human-in-the-Loop)**: A gate type requiring an explicit, recorded human approval or rejection decision before a state-changing action (e.g. infrastructure apply, PR merge) is allowed to proceed.
- **Spoke Agent**: One of the persistent core agents (Discovery, DevOps, Security, Modernization, Portfolio Assessment) or the on-demand PR-Reviewer agent, each implementing the `SpokeAgent.execute(envelope)` interface under its own least-privilege IAM role.
- **Task Envelope**: The bounded input structure (`task`, `inputs` as `ArtifactRef`s, `acceptanceCriteria`, `traceId`) passed to a Spoke Agent invocation; it never carries full run history inline.
- **RunState**: The durable, persisted record of a run's status, task graph, current step index, trace ID, and counters, used to make a run resumable after a halt or transient failure.
- **GateTicket**: The persisted record of a single HITL gate request, including its gate type, status (`PENDING`/`APPROVED`/`REJECTED`/`EXPIRED`), approval context, and held Step Functions task token.
- **Cost/Budget Counter Hook**: The deterministic (non-agentic) mechanism that enforces per-run hard ceilings on tokens, cost, wall-clock time, and steps, and that exposes the kill switch and Opus gate.
- **Deterministic Router**: The component that resolves a task type and attempt state to a model tier (Haiku/Sonnet/Opus) via a fixed policy table, escalating only on retry per a bounded ladder.
- **Opus Gate**: The check performed by `checkOpusGate(runId)` that allows an escalation to the Opus model tier only while the run's Opus invocation count remains below its configured maximum; it is a pure budget cap in Phase 1.
- **Circuit Breaker**: The per-agent mechanism triggered when a run detects repeated no-forward-progress activity or a configured number of consecutive `FAILED` `SpokeResult`s, stopping further retries for that agent until a human intervenes.
- **Step Functions Task Token**: The durable handle returned when a HITL gate's wait-for-task-token execution starts; `decide()` resumes the paused execution by calling `SendTaskSuccess`/`SendTaskFailure` against this token.

## Requirements

### Requirement 1: Hub/Supervisor orchestration

**User Story:** As a platform operator, I want a Supervisor that orchestrates agent work without performing migration actions itself, so that all state-changing work stays attributable to a specific spoke agent and auditable.

#### Acceptance Criteria

1. WHEN a run is started via `startRun(runConfig)` THEN the Supervisor SHALL decompose the run into a task graph across the five persistent core agents (Discovery, DevOps, Security, Modernization, Portfolio Assessment) without calling any MCP tool or cloud API directly.
2. WHEN the Supervisor routes a task THEN the Supervisor SHALL invoke the Deterministic Router (Requirement 3) before dispatching the task to any spoke agent.
3. IF an agent-to-agent handoff is required THEN the Supervisor SHALL broker the handoff itself (star topology) SO THAT no spoke agent calls another spoke agent directly.
4. WHEN `getRunStatus(runId)` is called THEN the Supervisor SHALL return a status that is one of `PENDING`, `RUNNING`, `HALTED`, `AWAITING_HITL`, `COMPLETED`, or `FAILED`, reflecting the true current state of the run's task graph.
5. WHEN `killRun(runId, reason)` is invoked THEN the Supervisor SHALL immediately stop routing further tasks for that run and drain/cancel any in-flight spoke invocations for that run.

### Requirement 2: Persistent core agents

**User Story:** As a migration engineer, I want the five persistent core agents (Discovery, DevOps, Security, Modernization, Portfolio Assessment) to each operate under least-privilege identity and a common structured contract, so that their outputs are verifiable and their permissions are auditable.

#### Acceptance Criteria

1. EACH core agent SHALL implement the `SpokeAgent.execute(envelope)` interface and return a `SpokeResult` containing `output`, `confidence`, `tokensUsed`, `status`, and `notes`.
2. WHEN a core agent is invoked THEN the agent SHALL receive only a `TaskEnvelope` (task, inputs as `ArtifactRef`s, acceptance criteria, trace ID) and SHALL NOT receive full run history inline.
3. EACH core agent SHALL run under its own dedicated least-privilege IAM role, distinct from the Supervisor's role and from every other agent's role.
4. WHEN the Discovery Agent collects inventory data THEN the system SHALL default to the Haiku model tier for collection tasks and the Sonnet tier for reasoning tasks, per the task→model policy.
5. WHEN the DevOps Agent generates Terraform or CI/CD workflow files THEN the DevOps Agent SHALL open a pull request via the GitHub MCP connector rather than applying changes directly.
6. WHEN the Security Agent evaluates a migration plan or Terraform plan THEN the Security Agent SHALL return either a pass result or a list of findings, and SHALL NOT itself approve or block the plan (approval remains a human HITL decision).

### Requirement 3: Deterministic Router with agentic escalation

**User Story:** As a cost-conscious platform operator, I want task-to-model routing to follow a fixed, auditable default policy and escalate only when necessary, so that model spend stays predictable and every escalation is explainable.

#### Acceptance Criteria

1. WHEN `resolveModel(taskType, attemptState)` is called with `attemptState.attemptNumber = 1` THEN the Router SHALL return the model tier defined for that `taskType` in the task→model policy table, with no escalation logic applied.
2. IF a `taskType` has no entry in the task→model policy table THEN the Router SHALL raise an error rather than silently defaulting to a tier.
3. WHEN a task is retried after low confidence or failure (`attemptState.attemptNumber > 1`) AND the previous tier was Haiku THEN the Router SHALL escalate to Sonnet.
4. WHEN a task is retried after low confidence or failure AND the previous tier was Sonnet AND the number of Sonnet retries exceeds the configured maximum THEN the Router SHALL request an Opus-gate decision before returning Opus.
5. IF the Opus-gate decision is `DENIED` THEN the Router SHALL raise a run-halt condition rather than returning a model tier.
6. IF a task has already been escalated to Opus and continues to fail THEN the Router SHALL raise a run-halt condition rather than escalating further.
7. THE Router SHALL never return a model tier lower than the tier most recently used for the same task within the same run (monotonic escalation).
8. WHEN an escalation occurs (Haiku→Sonnet or Sonnet→Opus) THEN the calling component SHALL log the escalation with task ID, source tier, target tier, and reason.

### Requirement 4: Cost/Budget Counter Hook and kill switch

**User Story:** As a platform operator, I want a deterministic mechanism that enforces hard per-run limits on tokens, cost, time, and steps, and that can immediately halt a run, so that a misbehaving or looping agent run cannot consume unbounded resources.

#### Acceptance Criteria

1. WHEN `preCheck(runId, estimatedTokens)` is called AND the run's kill switch is active THEN the hook SHALL return a `HALT` decision without evaluating any other threshold.
2. WHEN `preCheck` is called AND projected total tokens, current cost, current wall-clock time, or current step count would exceed the run's configured ceiling THEN the hook SHALL return a `HALT` decision identifying which ceiling was breached.
3. IF all thresholds are within their configured ceilings THEN `preCheck` SHALL return an `OK` decision.
4. THE `preCheck` function SHALL NOT mutate any run state (read-only / side-effect-free).
5. WHEN `recordUsage(runId, agentId, tokensIn, tokensOut, wallClockMs)` is called THEN the hook SHALL atomically increment the run's counters (`totalTokensIn`, `totalTokensOut`, `totalWallClockMs`, `totalSteps`, `estimatedCostUsd`).
6. IF `recordUsage` is called more than once with the same invocation idempotency key THEN the run's counters SHALL reflect the usage exactly once (idempotent).
7. WHEN `checkOpusGate(runId)` is called AND the run's Opus invocation count has reached the configured maximum THEN the hook SHALL return `DENIED`.
8. WHEN `checkOpusGate(runId)` is called THEN the hook SHALL return `ALLOWED` if and only if the run's Opus invocation count is below the configured maximum (a pure budget cap); Phase 1 SHALL NOT implement a HITL-override path that grants an Opus invocation beyond this cap (deferred to Phase 2, where a dedicated Opus/cost-escalation gate type may be introduced rather than reusing an unrelated gate).
9. WHEN a `HALT` decision is returned from `preCheck` THEN the calling pipeline SHALL halt the run and raise a HITL alert rather than continuing execution.
10. WHEN the hook detects repeated identical tool/agent calls with no forward progress in the run's task graph (bounded lookback window) THEN the hook SHALL trigger that agent's circuit breaker.
11. WHEN a global kill switch is activated for a run THEN every subsequent `preCheck` call for that run SHALL return `HALT`, and no new spoke invocation for that run SHALL start.
12. WHEN an agent records a configured number (N) of consecutive `FAILED` `SpokeResult`s for a run THEN the hook SHALL trigger that agent's circuit breaker; this trigger is independent of, and in addition to, the no-forward-progress detection in Criterion 10 (the two are distinct triggers feeding the same circuit-breaker mechanism).

### Requirement 5: HITL Approval Broker (7 gates)

**User Story:** As a compliance-conscious platform operator, I want every state-changing action gated by an explicit, auditable human approval step, so that no infrastructure change, merge, destructive action, worker spin-up, KB write, plan finalization, or cloud deploy happens without a recorded human decision.

#### Acceptance Criteria

1. THE system SHALL implement exactly seven HITL gate types: infrastructure apply, PR merge, destructive action, on-demand worker spin-up, KB write, migration-plan/blueprint finalization, and cloud deploy.
2. WHEN a task reaches an action requiring one of the seven gates THEN the system SHALL call `raiseGate(gate, runId, context)`, which SHALL start an AWS Step Functions execution that pauses using the "wait for task token" pattern, and SHALL block that action until the resulting ticket is resolved via `decide()` calling `SendTaskSuccess` or `SendTaskFailure` against the held task token (per design.md Component 4); no Lambda invocation SHALL hold a blocking call open for the duration of the wait.
3. WHEN a gate ticket is raised THEN the run's status SHALL become `AWAITING_HITL` for the entire run (Phase 1 is run-level blocking, not per-task blocking — Phase 1's task graph is effectively linear, so no unrelated task within the same run SHALL continue to progress while any ticket for that run is `PENDING`), and the ticket SHALL be persisted before any notification is sent.
4. WHEN `decide(ticketId, decision, approver)` is called on a ticket whose status is not `PENDING` THEN the system SHALL reject the call rather than silently applying the decision.
5. WHEN a ticket is decided `APPROVED` THEN the system SHALL persist the decision, write an audit event, set the run's status back to `RUNNING`, and resume exactly the task blocked on that ticket by calling `SendTaskSuccess` against the ticket's held Step Functions task token.
6. WHEN a ticket is decided `REJECTED` THEN the system SHALL halt the run and SHALL NOT resume or work around the blocked action.
7. EVERY gate decision (approve or reject) SHALL be written to the audit log with ticket ID, approver identity, and decision timestamp before the blocked task resumes.
8. Phase 1 SHALL NOT implement per-gate approver RBAC or approval-expiry/timeout behavior (explicitly deferred to Phase 2 per the source design); any authenticated portal user may decide any gate in Phase 1.

### Requirement 6: Pre/post agent-invocation hook pipeline

**User Story:** As a platform operator, I want every spoke agent invocation to pass through a consistent pre- and post-invocation pipeline, so that guardrails, budget checks, HITL gates, schema validation, and audit logging are enforced uniformly rather than per-agent.

#### Acceptance Criteria

1. BEFORE any spoke agent's model call executes, the pipeline SHALL attach Bedrock Guardrails, attach the cached system/policy prompt, and enforce that agent's tool allowlist.
2. BEFORE any spoke agent's model call executes, the pipeline SHALL call the Cost/Budget Counter Hook's `preCheck` and SHALL NOT proceed to invocation if the result is `HALT`.
3. BEFORE any spoke agent's model call executes, the pipeline SHALL check for a blocking HITL gate applicable to that task type and, if found, SHALL block until the gate is resolved.
4. IF a blocking HITL gate is rejected THEN the pipeline SHALL return a `FAILED` result and SHALL NOT invoke the agent's model call.
5. AFTER a spoke agent's model call returns, the pipeline SHALL validate the result against that agent's output schema before accepting the result.
6. IF output schema validation fails THEN the pipeline SHALL return a `FAILED` result and SHALL NOT record it as a successful completion.
7. AFTER a successful invocation, the pipeline SHALL call `recordUsage` on the Cost/Budget Counter Hook, write exactly one audit event, and trigger memory summarize-and-evict.
8. IF the returned result's confidence is below the configured confidence threshold THEN the pipeline SHALL retry the task through the Router's escalation ladder (Requirement 3) rather than accepting a low-confidence result as final.
9. THE retry behavior in Criterion 8 SHALL terminate (via the Router's bounded escalation ladder) rather than recursing indefinitely.

### Requirement 7: Deterministic CI/CD execution path

**User Story:** As a migration engineer, I want the actual migration execution (build, apply, deploy, smoke test) to run through deterministic CI/CD rather than an autonomous agent, so that Phase 1 execution is predictable, reviewable, and does not require a new class of agentic risk before it's justified.

#### Acceptance Criteria

1. WHEN the DevOps Agent completes Terraform and GitHub Actions workflow generation THEN the change SHALL be submitted as a pull request, not applied directly.
2. WHEN a pull request affecting infrastructure is opened THEN deterministic checks (format/validate, lint, policy/security scan, plan output) SHALL run and post results before a human reviews the PR.
3. WHEN a pull request is opened THEN the PR-Reviewer Agent SHALL post an advisory comment (risk score, diff summary, KB conformance, focus list, cost delta) and SHALL NOT merge or approve the PR itself.
4. WHEN a human merges the PR (HITL gate: PR merge) AND a human approves the infrastructure apply (HITL gate: infrastructure apply) THEN GitHub Actions SHALL run `terraform apply` using the S3-backed remote state with native state locking.
5. WHEN a human approves the cloud-deploy gate THEN GitHub Actions SHALL deploy the built container image to ECS Fargate.
6. AFTER deployment completes THEN a scripted (non-LLM) smoke-test CI step SHALL execute a health-endpoint check and basic functional check, and SHALL report pass/fail back to the Hub's audit log.
7. IF the scripted smoke test fails THEN the pipeline SHALL halt and raise a HITL alert, and SHALL NOT attempt autonomous remediation.
8. GitHub Actions SHALL authenticate to AWS via OIDC federation to a scoped IAM role, and SHALL NOT use long-lived AWS access keys stored as Actions secrets.

### Requirement 8: Durable, resumable run state

**User Story:** As a platform operator, I want run state to be persisted at every step boundary, so that a transient failure does not corrupt state, strand resources, or require restarting the entire run from scratch.

#### Acceptance Criteria

1. WHEN a run transitions between task-graph steps THEN the updated `RunState` (including `taskGraph`, `currentStepIndex`, and `counters`) SHALL be persisted before the next step begins.
2. EVERY agent/tool action that could be re-executed on retry (e.g. `terraform apply`, deploy, KB write) SHALL carry an idempotency key, and re-execution with the same key SHALL NOT double-apply the action.
3. WHEN a transient tool, model, or throttling error occurs THEN the system SHALL retry the failed operation with exponential backoff up to a configured maximum retry count, and IF retries are exhausted THEN the system SHALL persist the failed invocation's context (task envelope reference, error detail, retry count, trace ID) as a dead-letter record in a durable store (DynamoDB) rather than discarding it, and SHALL raise a HITL alert referencing the dead-letter record.
4. WHEN a run halts partway through a state-changing sequence THEN a defined compensation action for that sequence (e.g. `terraform destroy` of the just-applied module) SHALL be available, and executing that compensation action SHALL itself require raising the `DESTRUCTIVE_ACTION` HITL gate (Requirement 5) and SHALL NOT execute until that gate is `APPROVED`.
5. WHEN a run resumes after a halt THEN the resumed run SHALL NOT re-execute steps already marked complete in the persisted `taskGraph`, and SHALL NOT double-count usage already recorded in `RunCounters`.

### Requirement 9: Knowledge, memory, and guardrails

**User Story:** As a platform operator, I want all agents grounded in the authoritative corporate knowledge base with advisory AWS documentation, backed by short/long-term memory and safety guardrails, so that agent outputs are consistent with corporate policy and safe by default.

#### Acceptance Criteria

1. WHEN an agent needs corporate guidance THEN it SHALL retrieve top-k chunks (not the whole KB) from the Bedrock Knowledge Base backed by S3 and the S3 Vectors vector store.
2. IF the corporate KB and AWS Documentation MCP guidance conflict THEN the agent SHALL follow the corporate KB, SHALL record the conflict (KB guidance, AWS Docs guidance, and the KB-following decision) in the `SpokeResult.notes` field, and SHALL cause the pipeline to write a dedicated `kb_conflict_flagged` audit event correlated to the run's trace ID, rather than silently following AWS best-practice guidance or omitting the conflict from any record.
3. EVERY Bedrock model call made by any agent SHALL pass through Bedrock Guardrails (PII redaction, prompt-injection defense, denied topics, grounding checks).
4. WHEN a run closes THEN the working memory for that run SHALL be summarized and evicted into AgentCore long-term memory rather than retained as a raw transcript.
5. ALL MCP tool output and any discovered source code SHALL be treated as untrusted data by agents, not as instructions.

### Requirement 10: Observability and audit trail

**User Story:** As a platform operator, I want every agent action and human decision traceable end-to-end through a single run/trace ID, so that any run's behavior can be reconstructed after the fact.

#### Acceptance Criteria

1. WHEN a run starts THEN a single trace ID SHALL be generated and propagated in every task envelope and audit event for that run.
2. EVERY completed agent invocation (success or failure) SHALL produce exactly one audit event correlated to the run's trace ID.
3. EVERY HITL gate decision SHALL produce exactly one audit event correlated to the run's trace ID.
4. THE system SHALL support reconstructing the full sequence of actions for a given run from the audit log alone, without requiring access to raw model transcripts.
5. PER-AGENT metrics (latency, token/cost usage, escalation occurrences, tool error rate) SHALL be recorded per invocation.

### Requirement 11: Identity, secrets, and tool authorization

**User Story:** As a security-conscious platform operator, I want agent identities, secrets, and tool access scoped and enforced mechanically, so that no agent can exceed its intended permissions even if instructed to by a prompt.

#### Acceptance Criteria

1. EACH agent and worker SHALL run under its own least-privilege IAM role; no two agents SHALL share a role, and the Supervisor's role SHALL NOT include migration-action permissions.
2. ALL credentials (GitHub token, Azure service principal, registry credentials) SHALL be stored in AWS Secrets Manager and injected at tool-call time only.
3. CREDENTIALS SHALL NOT appear in prompts, context, memory, or logs at any point.
4. WHEN an agent attempts to call an MCP tool outside its configured allowlist THEN the pre-invocation hook SHALL block the call, independent of what the agent's prompt instructs.
5. EACH MCP server used SHALL be a vetted, version-pinned build, and its output SHALL be treated as untrusted data by consuming agents.

### Requirement 12: Minimal DAF Portal

**User Story:** As a platform operator, I want a minimal portal to kick off runs, monitor progress, and act on HITL approvals, so that I don't need direct API/CLI access to operate Phase 1.

#### Acceptance Criteria

1. THE portal SHALL allow an authenticated user to start a new migration run for the synthetic application.
2. THE portal SHALL display live run status, including current task-graph step and any `AWAITING_HITL` state.
3. WHEN a HITL gate ticket is raised THEN the portal SHALL surface it to authenticated users with enough context (artifact references, summary) to make an approval decision.
4. THE portal SHALL authenticate users via Amazon Cognito and SHALL NOT expose any run-control action to unauthenticated requests.
5. Phase 1 portal scope SHALL exclude KB management UI, blueprint viewer, cost dashboard, and full audit-trail UI (explicitly deferred to Phase 2 per the source design).

## Out of Scope for Phase 1

The following are explicitly excluded from this requirements set, per the design document's Phase 1/Phase 2 boundary, and MUST NOT be treated as implicit requirements:

- Migration Worker agent, agentic Testing/Validation agent, full Cost/FinOps agent, KB-Curator agent.
- OpenSearch Serverless as a KB vector backend (S3 Vectors only in Phase 1).
- Sandboxed ephemeral execution of agent-generated code; VPC/PrivateLink network isolation; cross-account compute topology.
- EKS and Azure redeploy targets (ECS Fargate only in Phase 1).
- Per-gate approver RBAC, approval-expiry/timeout policies.
- Full portal (KB management, blueprint viewer, cost dashboard, audit-trail UI).
- Data classification/retention policy for discovered source data, multi-tenancy isolation, audit immutability/WORM retention, formal NFR targets — all remain open items per the source design (§14) and are not addressed by Phase 1 requirements.
