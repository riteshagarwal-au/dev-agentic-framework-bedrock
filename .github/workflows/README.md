# .github/workflows/

## Ownership

This directory contains the **GitHub Actions workflow definitions** that implement DAF Phase 1's
deterministic CI/CD execution path.

Owned by: Cloud/Platform (DevOps) engineering (same ownership as `infra/`).

## Scope

Per design.md "Component 6: Deterministic CI/CD path" and requirements.md Requirement 7, this
directory will hold:

- **Deterministic PR checks** — `terraform fmt`/`validate`, `tflint`, `checkov`/`tfsec`, and posting
  `terraform plan` output as a PR comment, triggered on any infrastructure-affecting PR.
- **Terraform plan/apply workflow** — gated by the PR-merge and infra-apply HITL gates; authenticates
  to AWS via OIDC federation (no long-lived keys) against the state backend defined in `infra/`.
- **Container build/deploy workflow** — builds/pushes the container image and deploys to the ECS
  Fargate target, gated on the cloud-deploy HITL approval.
- **Scripted (non-LLM) smoke-test step** — deterministic health-endpoint and functional check
  post-deploy, reporting pass/fail back to the Hub's audit log; halts and raises a HITL alert on
  failure rather than attempting autonomous remediation.

## Out of scope

- The Terraform/IaC these workflows operate on (see `infra/`).
- The Python backend and agent logic these workflows' deterministic checks and audit reporting call
  into (see `backend/`).
- The PR-Reviewer Agent's *advisory* review logic itself (implemented in `backend/`); these workflows
  only trigger it and post its output as a PR comment.

No workflow in this directory performs an unreviewed `apply`/deploy — every state-changing workflow
run is gated by a HITL approval recorded via the HITL Approval Broker (`backend/`).

See [`../../.kiro/specs/daf-phase1-foundations/design.md`](../../.kiro/specs/daf-phase1-foundations/design.md)
for the full component design.
