---
mode: agent
description: Structured bug investigation and resolution — root cause analysis, then fix design, then implementation tasks. Matches Kiro IDE's "Bug Fix" workflow.
---

# Bug Fix workflow

Investigate and resolve a bug through three structured phases: **root cause
analysis → fix design → implementation tasks**. Ground every step in evidence from
the codebase, logs, or reproduction steps — never guess at a cause.

## Input

- **Bug**: `${input:bug:Description of the bug, error message, or issue reference}`

## Phase 1 — Root Cause Analysis

1. Reproduce or trace the issue: read the relevant code, error messages, stack
   traces, logs, or tests.
2. Create `.kiro/specs/<bug-slug>/root-cause.md`:
   - **Symptom**: what's observed (error, wrong output, crash).
   - **Reproduction steps** (if determinable).
   - **Root cause**: the precise underlying defect, with file/line references.
   - **Impact/scope**: what else might be affected by the same defect.
3. **Stop.** Present the root cause to the user for confirmation before designing a
   fix.

## Phase 2 — Fix Design

1. Once the root cause is confirmed, create `.kiro/specs/<bug-slug>/fix-design.md`:
   - The proposed fix and why it addresses the root cause (not just the symptom).
   - Any alternative approaches considered and why they were rejected.
   - Risk of regression and how it will be mitigated (tests, guards).
2. **Stop.** Ask the user to approve the fix approach before creating tasks.

## Phase 3 — Tasks

1. Create `.kiro/specs/<bug-slug>/tasks.md`: checkbox tasks for the fix itself, a
   regression test that fails before the fix and passes after, and any related
   cleanup.
2. **Stop.** Ask the user to approve before implementation begins.

## Constraints

- Do not propose a fix before the root cause is confirmed.
- Every fix must include a regression test task.
- Planning artifacts only in this workflow — implementation happens afterward.
