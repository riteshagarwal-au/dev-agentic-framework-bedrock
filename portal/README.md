# portal/

## Ownership

This directory contains the **React/TypeScript single-page application** for the DAF Portal, Phase 1.

Owned by: Frontend/Portal engineering.

## Scope

This is the minimal Phase 1 run-control surface, including:

- **Run kickoff view** — start a new migration run for the synthetic application.
- **Live run-status monitoring view** — current task-graph step, run status, `AWAITING_HITL` state.
- **HITL approval ticket list and decision view** — pending gate tickets with artifact
  references/summary context, and an approve/reject action.
- **Cognito-authenticated API client and route guards** — every run-control call requires an
  authenticated session; unauthenticated requests never reach a run-control action.

## Out of scope (Phase 1)

Per the Phase 1/Phase 2 scope boundary (design.md, requirements.md Requirement 12.5):

- KB management UI, blueprint viewer, cost dashboard, full audit-trail UI.
- Any business logic beyond a thin authenticated CRUD/monitoring surface over the backend APIs
  (see `backend/` for the API Gateway + Lambda endpoints this app calls).

See [`../.kiro/specs/daf-phase1-foundations/design.md`](../.kiro/specs/daf-phase1-foundations/design.md)
for the full component design.

## Scaffold

Built with [Vite](https://vite.dev/) (`react-ts` template) + ESLint. No business logic yet —
this is pure build/test/lint tooling setup (Task 1.4).

Scripts:

- `npm run dev` — start the Vite dev server.
- `npm run build` — type-check (`tsc -b`) and produce a production build in `dist/`.
- `npm test` — run the Vitest test suite once (CI-friendly, non-watch).
- `npm run lint` — run ESLint.
- `npm run format` / `npm run format:check` — apply / check Prettier formatting.
