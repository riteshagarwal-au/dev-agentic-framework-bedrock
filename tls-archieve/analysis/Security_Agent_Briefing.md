# Security Agent — Briefing Document

**Purpose:** Consolidated reference on the "Security Agent" concept for the upcoming group call.

**Note:** This is a single engagement, not two — [WO-022537_Design_Document.md](WO-022537_Design_Document.md) was our earlier design/assessment based on the original SOW; the TAAF exec summary is the more recent document for the same engagement as the design has evolved. Where the two differ below, treat WO-022537 as the earlier position and TAAF as the current/updated one.

**Sources:**
- [WO-022537_Design_Document.md](WO-022537_Design_Document.md) — earlier design (§5.2 Security Agent, §5.6 Deterministic-First alternative, §7 Security & Compliance)
- [Telstra_AWS_Agentic_Framework_TAAF_v03_ExecSum_Review.md](../Telstra_AWS_Agentic_Framework_TAAF_v03_ExecSum_Review.md) — current exec summary (§12 Secure Deployment Architecture, §15 Transformation Impact, §16 Afterburner Trial Results)

---

## 1. What the Security Agent does

| Document | Function |
|---|---|
| WO-022537 (earlier design) | Policy/compliance checks against AWS Provider Security Policy, access/isolation boundary enforcement, internet-exposure scanning, audit logging |
| TAAF (current) | Validates designs/code against Telstra Cloud Security Baselines (SAD review), runs automated PEN testing with self-adaptive attack chaining, produces audit-ready evidence with reasoning per finding |

The function is consistent across both: an agent that continuously checks a design/deployment against a defined security baseline, rather than a one-off manual review. TAAF reflects how this has matured since the earlier WO-022537 design — now with real trial evidence (§4 below).

## 2. Two competing design philosophies

### A. Fully agentic (current baseline design in both docs)
- Security Agent reasons over code/config/deployment and makes judgment calls about compliance and vulnerabilities.
- TAAF's PEN-testing agent is explicitly **self-adaptive** — it dynamically selects attack vectors based on code and deployment, with an LLM-as-judge validating finding integrity.
- Faster and more flexible, but relies on the model's reasoning to be correct — harder to audit/prove deterministically.

### B. Deterministic-first (WO-022537 §5.6, informed by CBA "Lumos" re:Invent 2025 case study)
- Security compliance implemented as **hardcoded guardrails/policy-as-code** (deny internet-facing resources, enforce IAM boundaries, block sensitive-data exposure) — deterministic, testable, auditable.
- AI is layered on top **only** for tasks that benefit from reasoning: interpreting scan results, summarizing risk, generating security documentation/threat tables — **not** for making enforcement decisions itself.
- Rationale: reduces hallucination risk, gives an auditable/provable compliance story, better fit where there's a formal Change-approval requirement or explicit contractual security clauses.
- Read-mostly by default in WO-022537's original design; any remediation action requires escalation/approval rather than autonomous execution.

**This is likely the central discussion point for the call** — whether Security Agent should reason autonomously (TAAF's current direction) or sit on top of deterministic policy-as-code (WO-022537's proposed alternative), or a hybrid.

## 3. Guardrails & control model

| Control | WO-022537 (earlier design) | TAAF (current) |
|---|---|---|
| Human-in-the-loop | Any remediation action requires escalation/approval, not autonomous execution | Feedback loop: agent flags gaps → developer remediates → agent re-validates |
| Change approval | Written Engagement Manager approval required before any Change (clause 5) | Not explicitly restated in the TAAF exec summary |
| Data/scope boundary | No AWS Information internet-accessible (cl. 4.1); AWS Provider Security Policy compliance (cl. 4.2) | AU-CRIS compliant, Sydney-region only, zero data retention, session-isolated microVMs, no model training on customer data |
| Enforcement mechanism | Proposed: policy-as-code as the enforcement layer, AI advisory only (§5.6 alternative) | Cedar policy enforcement (deterministic auth outside LLM reasoning) sits alongside agentic reasoning |

The change-approval requirement (clause 5) from the earlier WO-022537 design should still apply going forward — confirm it hasn't been dropped, just left implicit in the newer TAAF material.

Note both designs already agree on one principle: **deterministic enforcement of hard boundaries (data exposure, encryption, network isolation) should not depend on LLM reasoning** — TAAF does this via Cedar policy + VPC/KMS controls; WO-022537's §5.6 proposes the same idea more broadly (extending it to compliance/security checks generally, not just infra boundaries).

## 4. Evidence — Afterburner trial (new since the earlier WO-022537 assessment)

2-week trial, Telstra Afterburner team, March 2026, tested against 20 Cloud Security Baselines:

- **SAD generation:** 2 days (vs. weeks manually)
- **PEN testing:** 3.5–7 hours per test (vs. 3 weeks / $25–50K manual), on-demand at $300–$500/test
- **Coverage:** continuous PEN testing on every release vs. one-off testing at ATO/ORC only (81% of teams reportedly ship known-vulnerable code to meet deadlines under the manual process)
- **Novel finding:** discovered a multi-WAF/load-balancer attack vector not covered by existing baselines — fed back to Security Engineering to assess whether a new baseline is needed (a good example of agentic value-add beyond baseline checklist compliance)
- **Outcome:** developers self-sufficient in aligning to security standards without needing to be security experts; eliminated dependency on resource-constrained Cyber Assurance teams

This trial evidence didn't exist at the time of the earlier WO-022537 assessment — it's the strongest validation to date that the design direction works, and should inform how we scope the (still single-application) pilot referenced in WO-022537.

## 5. Talking points / questions for the group call

1. **Autonomy level:** Do we standardize on fully agentic reasoning (TAAF's current direction) or adopt the deterministic-first pattern (WO-022537 §5.6) for security enforcement specifically?
2. **Evidence requirement:** Should every Security Agent deployment require a trial period (like Afterburner) before being trusted for autonomous PEN testing/compliance sign-off?
3. **Escalation model:** WO-022537 has explicit contractual change-approval gates; TAAF's deck doesn't show an equivalent formal gate for security remediation — should we standardize this across engagements?
4. **Baseline drift:** TAAF's trial surfaced a security baseline gap (multi-WAF vector) the agent found but the baseline didn't cover — how do we formalize a feedback loop from agent findings back into baseline/policy updates?
5. **Data residency/model training:** TAAF's AU-CRIS/no-training constraints are strict and specific — confirm whether WO-022537's environment has equivalent requirements, since its design doc doesn't currently address data residency at that level of detail.
6. **Cost model:** TAAF prices PEN tests at $300–$500 on-demand; useful benchmark to bring into WO-022537 commercial discussions if a similar on-demand security testing capability is proposed there.
