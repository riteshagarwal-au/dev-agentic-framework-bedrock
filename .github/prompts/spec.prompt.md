---
mode: agent
description: Structured feature development with approval gates — requirements, then design, then tasks. Matches Kiro IDE's "Spec" workflow.
---

# Spec workflow

Run structured, spec-driven development for a feature: **requirements → design →
tasks**, with an explicit approval gate after each phase. Do not skip a gate and do
not write implementation code during this workflow — it only produces planning
artifacts.

## Input

- **Feature**: `${input:feature:Short feature name or description}`

## Phase 1 — Requirements

1. If the feature description is too ambiguous to write testable criteria, ask
   clarifying questions first. Otherwise infer reasonable scope.
2. Create `.kiro/specs/<feature-slug>/requirements.md`:
   - **Introduction**: one paragraph describing the feature and its goal.
   - Numbered **Requirements**, each with:
     - A user story: "As a `<role>`, I want `<capability>`, so that `<benefit>`."
     - **Acceptance Criteria** in EARS form, numbered `X.Y`:
       - `X.Y WHEN <trigger> THE SYSTEM SHALL <response>.`
       - `X.Y IF <precondition> THEN THE SYSTEM SHALL <response>.`
   - Cover happy paths, edge cases, error handling, and any non-functional constraints.
3. **Stop.** Show the user the requirements and ask them to approve or request
   changes. Do not proceed to design until they explicitly approve.

## Phase 2 — Design

1. Read the approved `requirements.md`. Every design decision must trace back to a
   requirement number.
2. Do any necessary research (existing code, libraries, patterns) and summarize
   findings inline.
3. Create `.kiro/specs/<feature-slug>/design.md` with:
   - **Overview**, **Architecture** (Mermaid diagram), **Components and Interfaces**,
     **Data Models**, key **Algorithms**, **Sequence Diagrams** (Mermaid) for
     important flows, **Error Handling**, **Testing Strategy**.
   - Cross-reference requirement numbers throughout.
4. **Stop.** Ask the user to approve or request changes before moving on.

## Phase 3 — Tasks

1. Read the approved `requirements.md` and `design.md`.
2. Create `.kiro/specs/<feature-slug>/tasks.md`: an ordered, checkbox implementation
   plan where each task:
   - Is a checkbox: `- [ ] N. <imperative task title>`.
   - Has concrete, code-level sub-bullets.
   - Cites `_Requirements: X.Y_` and references the design section it implements.
   - Builds only on earlier tasks (bottom-up: shared contracts/models first).
3. **Stop.** Ask the user to approve. Once approved, tell them they can begin
   implementation task-by-task in a normal Agent chat, or via `/execute-plan` if that
   prompt is available.

## Constraints

- One phase at a time; never skip an approval gate.
- Never write feature/application code in this workflow — planning artifacts only.
- All three files live under `.kiro/specs/<feature-slug>/`.
