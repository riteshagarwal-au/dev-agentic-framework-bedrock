# DAF Phase 1 — Spec Review Findings

**Reviewed:** 2026-08-20
**Scope:** `.kiro/specs/daf-phase1-foundations/` — `requirements.md`, `design.md`, `tasks.md`
**Reviewer summary:** Strong, disciplined spec set. EARS requirements, pseudocode algorithms, and tasks are tightly cross-referenced, and the Phase 1/Phase 2 scope boundary is consistently enforced across all three documents. The findings below are ordered by importance, followed by coverage gaps and minor inconsistencies.

---

## Correctness / logic issues

### 1. `checkOpusGate` has an unreachable branch and never enforces HITL approval
**File:** `design.md` — Algorithm 2, `checkOpusGate`

```pascal
IF counters.opusInvocations >= ceiling.maxOpusInvocations THEN
    RETURN OpusGateDecision(DENIED, ...)
END IF
...
IF hitlApproved OR counters.opusInvocations < ceiling.maxOpusInvocations THEN
    RETURN OpusGateDecision(ALLOWED, "")
END IF
RETURN OpusGateDecision(DENIED, "no HITL approval and budget exhausted")
```

After the first guard, `opusInvocations < maxOpusInvocations` is **always** true, so the second `IF` always returns `ALLOWED` and the final `DENIED` is dead code. Net effect: the Opus gate only enforces the count cap and **never actually requires a human approval**, which undercuts Requirement 3.4 ("request an Opus-gate decision") and the spirit of Requirement 4.8.

**Action:** Decide whether Opus needs HITL-**or**-budget (current req wording) or HITL-**and**-budget, and rewrite so the intent is enforceable. Note: Property 3 (task 8.7) will pass against the current logic without ever exercising the approval path.

### 2. Opus approval reuses `DESTRUCTIVE_ACTION` gate as a proxy
**File:** `design.md` — Algorithm 2, `checkOpusGate`

The comment concedes this is a hack (`Opus escalation reuses the closest applicable gate context`). There are only 7 defined gate types and none is an "Opus/cost escalation" gate, so this conflates two distinct human decisions in the audit trail.

**Action:** Either add an explicit gate type or document that Opus escalation deliberately has no dedicated gate in Phase 1.

### 3. `preCheck` projects tokens and steps but not cost or wall-clock
**File:** `design.md` — Algorithm 2, `preCheck`

The token check adds `estimatedTokens` and the steps check adds `+1`, but cost and wall-clock compare **current** counters only. A single call can therefore push `estimatedCostUsd` or `totalWallClockMs` past its ceiling before the next `preCheck` catches it. Correctness Property 2 claims caps hold "at all observed points in time (not just at halt)" — not strictly true for cost/time under the current pseudocode.

**Action:** Either weaken the property statement or project cost/time like tokens.

---

## Architecture gap

### 4. Synchronous `BLOCK UNTIL ticket resolved` is incompatible with the stated API Gateway + Lambda runtime
**File:** `design.md` — Algorithm 4 (hook pipeline) and Algorithm 3 (`decide`)

The hook pipeline does `BLOCK UNTIL HitlBroker ticket resolved`, and `decide()` does `RESUME task blocked on ticket`. HITL gates can stay pending for hours/days. The design labels this a "resumable wait, not a busy-loop" but never names a durable orchestration mechanism (Step Functions, or a re-entrant Supervisor driven off DynamoDB state). Given the run must be resumable (Req 8.1/8.5) and the compute is Lambda, a blocking call cannot be held.

**Action:** Make an explicit execution-engine decision. This is the biggest unresolved design question and is not currently captured as a task or an open item.

### 5. Whole-run vs. per-task blocking is contradictory
**File:** `design.md` — Model 3 validation vs. `raiseGate`; `requirements.md` Req 5.3

Model 3 validation says a `PENDING` ticket "blocks the specific task that raised it… not the whole run, unless… on the critical path," but `raiseGate` unconditionally sets `RunState.status ← AWAITING_HITL` and Req 5.3 makes it a run-level status. Fine for a linear Phase 1 task graph, but the spec asserts both models.

**Action:** Pick one model and state it consistently.

---

## Requirements not covered by any task

These EARS criteria have no corresponding task in `tasks.md`:

- **Req 8.3** — transient-error retry with backoff + dead-letter store. No task implements backoff/DLQ.
- **Req 8.4** — compensation path (e.g. HITL-gated `terraform destroy`). Described only in Error Scenario 4; no task builds it.
- **Req 9.2** — on KB vs. AWS-Docs conflict, follow corporate KB and flag the deviation. Modernization (task 13.4) wires both sources, but no task implements the conflict-resolution / flag behavior.

**Action:** Add tasks for these, or explicitly move them to an "accepted risk / deferred" note.

---

## Minor inconsistencies

- **Task 6.1** cites `_Requirements: 2.2, 4.4 (data model portion)_`, but Req 4.4 is "`preCheck` SHALL NOT mutate state" — a behavioral rule, not a data model. Likely meant a `BudgetCeiling`/`RunCounters` criterion.
- **Circuit breaker** (`triggerCircuitBreaker`) is invoked in `recordUsage` but is not in the `CostBudgetHook` interface signature (Component 3). Error Scenario 3 also mentions an "N consecutive failures" breaker distinct from `detectRepeatedNoProgress`, but only the no-progress detector is specified/tasked (8.4). Clarify whether these are one mechanism or two.
- **`tasks.md` ends mid-item at 18.2** with no closing / coverage summary. Confirm it was not truncated, and consider a final "requirements traceability" check task since the spec is otherwise meticulous about it.
- **`EXPIRED` gate status** is defined in the model but explicitly never populated in Phase 1 — intentional and documented; flagged only for awareness.

---

## Strengths worth keeping

- Correctness Properties 1–8 map cleanly to property-based test tasks (5.6, 7.4, 8.6–8.9, 9.5, 10.5) — excellent invariant → test traceability.
- Deterministic-first framing (agents author, GitHub Actions executes; OIDC not long-lived keys; Terraform ≥1.11 S3-native locking) is consistent and technically correct across all three docs.
- Scope discipline: every "Out of Scope" item in requirements has a matching Phase 2 column in the design table, and no task accidentally implements it.
