# Project steering

This file is loaded automatically into every Copilot Chat request for this
workspace — the equivalent of Kiro's steering files (`.kiro/steering/*.md`).

Use it to record durable, project-wide context: conventions, architecture rules,
tech stack, and working style. Keep entries short and factual; this file is read on
every request, so avoid anything that isn't broadly useful.

## How to use this file

- Add sections below as the project's conventions become clear (stack, folder
  layout, testing commands, style rules, domain rules that must never be violated).
- Prefer editing this file over creating new instruction files, unless a rule only
  applies to a specific file type or folder — use `.github/instructions/*.instructions.md`
  with an `applyTo` glob for those instead.
- Keep this file in sync with reality; remove guidance that's no longer true.

## Spec-driven workflow

This workspace uses the same spec-driven flow as Kiro IDE, stored under
`.kiro/specs/<feature-slug>/`:

- `/spec` — structured requirements → design → tasks, with an approval gate after
  each phase.
- `/quick-spec` — the same three artifacts generated in one pass, no gates.
- `/bug-fix` — root cause analysis → fix design → tasks, for bug investigations.
- **Plan agent** (`.github/agents/plan.agent.md`) — read-only exploration and
  planning; switch to it before making changes when you want a plan first.

Task files use checkboxes (`[ ]` not started, `[x]` done, `[-]`/`[~]` in progress)
and cite the requirement numbers they satisfy (`_Requirements: X.Y_`).
