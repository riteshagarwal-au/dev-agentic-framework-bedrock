---
mode: agent
description: Fast spec workflow — auto-generates requirements, design, and tasks without approval gates. Matches Kiro IDE's "Quick Spec" workflow.
---

# Quick Spec workflow

Generate the full spec trilogy for a feature in one pass, with **no approval
gates** between phases. This is the fastest path to an implementation-ready plan.
Still produces planning artifacts only — no feature code.

## Input

- **Feature**: `${input:feature:Short feature name or description}`

## Procedure

1. **Requirements** — create `.kiro/specs/<feature-slug>/requirements.md`: an
   Introduction paragraph plus numbered requirements, each with a user story and
   EARS-style acceptance criteria (`X.Y WHEN/IF ... THE SYSTEM SHALL ...`).
2. **Design** — immediately create `.kiro/specs/<feature-slug>/design.md`: Overview,
   Architecture (Mermaid diagram), Components and Interfaces, Data Models,
   Algorithms, Sequence Diagrams, Error Handling, Testing Strategy — every part
   traceable to a requirement number.
3. **Tasks** — immediately create `.kiro/specs/<feature-slug>/tasks.md`: an ordered
   checkbox implementation plan, each task citing `_Requirements: X.Y_` and the
   design section it implements, ordered bottom-up.
4. Do not pause between phases. When all three files are written, present a short
   summary of all three artifacts to the user for review.

## Constraints

- Planning artifacts only — never write feature/application code.
- Infer reasonable scope for ambiguous requests rather than stopping to ask; note any
  assumptions made at the top of `requirements.md`.
- All three files live under `.kiro/specs/<feature-slug>/`.
