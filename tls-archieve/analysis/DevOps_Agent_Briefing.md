# DevOps Agent — Briefing Document

**Purpose:** Consolidated reference on the "DevOps Agent" concept for the upcoming group call.

**Note:** This is a single engagement, not two — [WO-022537_Design_Document.md](WO-022537_Design_Document.md) was our earlier design/assessment based on the original SOW; the TAAF exec summary is the more recent document for the same engagement as the design has evolved. Where the two differ below, treat WO-022537 as the earlier position and TAAF as the current/updated one.

**Sources:**
- [WO-022537_Design_Document.md](WO-022537_Design_Document.md) — earlier design (§5.1 DevOps Agent, §5.5 Orchestration Layer, §5.6 Deterministic-First alternative, §6 AI/ML Technology Approach)
- [Telstra_AWS_Agentic_Framework_TAAF_v03_ExecSum_Review.md](../Telstra_AWS_Agentic_Framework_TAAF_v03_ExecSum_Review.md) — current exec summary (§2 Operating Flow, §7–8 Scope, §12 Secure Deployment Architecture)

---

## 1. What the DevOps Agent does

| Document | Function |
|---|---|
| WO-022537 (earlier design) | IaC generation/validation, CI/CD pipeline automation, environment provisioning, drift monitoring |
| TAAF (current) | Cost optimisation & triage, feeding a (future-phase) CI/CD trigger; PaaS optimisation recommendations on GitLab push/pull; observability integration with New Relic (chatbot-style natural-language queries) |

There is a subtle but important **scope shift** between the two documents:
- WO-022537 framed the DevOps Agent as an **active execution/provisioning** agent (generates IaC, drives pipelines, provisions environments, monitors drift).
- TAAF has narrowed the near-term role toward **advisory/optimisation** — cost triage and PaaS optimisation recommendations surfaced on GitLab activity, with the actual **CI/CD trigger explicitly deferred to a future phase**. Deployment execution sits in the deterministic GitLab pipeline, not the agent.

This narrowing is itself worth flagging on the call — TAAF has effectively moved closer to the deterministic-first position (see §2).

## 2. Two competing design philosophies

### A. Fully agentic (WO-022537 §5.1 original framing)
- DevOps Agent independently generates IaC/pipeline changes and provisions environments, reasoning over telemetry and code.
- Tools: AWS CLI/SDK, Git operations, pipeline trigger APIs, telemetry/log queries.
- Faster and more flexible, but the agent makes infrastructure decisions — higher blast radius, harder to audit deterministically.

### B. Deterministic-first (WO-022537 §5.6, informed by CBA "Lumos" re:Invent 2025 case study)
- Keep a **deterministic deployment platform/pipeline** (IaC templates, CI/CD, approval gates) as the actual execution layer.
- AI is used only to **generate parameters/config/IaC drafts** that feed into that pipeline; every infra-impacting action still routes through human review + Engagement Manager approval (clause 5).
- Rationale: reduces hallucination risk on infrastructure changes, gives an auditable/provable change story, better fit where there's a formal Change-approval requirement.

**Where TAAF has effectively landed:** TAAF's current operating flow keeps the **GitLab CI/CD pipeline as the execution layer** and positions the DevOps Agent as cost/optimisation advisor feeding a future CI/CD trigger — i.e. it has drifted toward option B in practice, even though it isn't labelled that way. The open question for the call is whether we make that deterministic-first stance **explicit and intentional**, rather than an accident of phasing.

## 3. Guardrails & control model

| Control | WO-022537 (earlier design) | TAAF (current) |
|---|---|---|
| Human-in-the-loop | All infrastructure-impacting changes require human approval before execution | Recommendations surfaced on GitLab push/pull; CI/CD trigger deferred to future phase (execution not yet autonomous) |
| Change approval | Written Engagement Manager approval required before any Change (clause 5); §5.1 guardrail explicitly aligned to it | Not explicitly restated in the TAAF exec summary |
| Enforcement mechanism | Bedrock Guardrails; no agent action can make AWS Information internet-accessible; enforced via network/IAM boundaries, not prompt instructions | GitLab pipeline + AgentCore Policy/Gateway; TAAF Agents run headless via Step Functions/Lambda for GitOps inside customer VPC |
| Execution layer | Proposed (§5.6): deterministic pipeline executes; AI drafts config only | GitLab CI/CD pipeline is the execution layer; agent is advisory |

The change-approval requirement (clause 5) from the earlier WO-022537 design should still apply going forward — confirm it hasn't been dropped, just left implicit in the newer TAAF material. This matters more for DevOps than Security because DevOps actions are directly infrastructure-mutating.

## 4. Integration & operating context (TAAF current)

- **Position in the flow:** DevOps Agent sits **after** Code & IaC generation, testing, and the compare/feedback loop — it handles cost optimisation & triage, then feeds the (future-phase) CI/CD trigger toward a deployed workload, which loops feedback back to the design/baseline stage.
- **Observability:** DevOps integration with **New Relic** via chatbot-style natural-language queries into observability data. Depends on a New Relic environment with appropriate API access (listed as a key dependency).
- **Pilot:** DevOps Agent pilot with the **TCG AMP team** — PaaS optimisation recommendations triggered on GitLab push/pull, on 1 application, during the 8-week Non-Production Pilots phase (Aug–Sep 2026).
- **Runtime:** TAAF Agents run as **headless Step Functions/Lambda for GitOps** inside the Customer VPC, coordinated via AgentCore (Registry/Runtime/Identity/Gateway/Memory/Policy/Tools), with session-isolated microVMs and zero data retention.

## 5. Talking points / questions for the group call

1. **Autonomy level:** Do we adopt the deterministic-first pattern (WO-022537 §5.6) for DevOps explicitly — deterministic pipeline executes, agent only drafts IaC/config — or restore the fuller autonomous provisioning role from the original §5.1 framing?
2. **Scope shift:** TAAF has narrowed DevOps to cost/optimisation advisory with CI/CD deferred to a future phase. Is that the intended long-term scope, or just pilot-phase sequencing? Confirm what "future-phase CI/CD trigger" actually commits us to.
3. **Change approval:** WO-022537 §5.1 ties DevOps guardrails directly to contractual clause 5 (Engagement Manager approval). TAAF doesn't restate an equivalent gate — should we standardise this, especially before any autonomous CI/CD trigger is enabled?
4. **New Relic dependency:** DevOps agent value in TAAF hinges on New Relic API access. Is that environment/access confirmed for the pilot, and what's the fallback if it slips? (WO-022537 assumed AWS-native telemetry/log queries instead — reconcile the two.)
5. **Drift monitoring:** WO-022537 §5.1 lists drift monitoring as a DevOps function; TAAF's flow emphasises cost triage instead. Confirm whether drift monitoring is still in scope and, if so, whether it's deterministic or agentic.
6. **Blast radius vs. Security Agent:** DevOps actions are infrastructure-mutating (higher blast radius) while Security is read-mostly. This argues for DevOps being *more* deterministic than Security, not less — worth aligning the two agents' autonomy models deliberately rather than by default.
