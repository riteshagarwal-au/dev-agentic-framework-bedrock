# TAAF vs. WO-022537 — Design Evolution Comparison (Same Engagement)

**Note:** These are not two separate engagements — [WO-022537_Design_Document.md](WO-022537_Design_Document.md) was our earlier design/assessment based on the original SOW, and the TAAF exec summary is the more recent document covering the same engagement as it has evolved. This comparison tracks how the design has moved on since the earlier assessment.

**Compared documents:**
- [WO-022537_Design_Document.md](WO-022537_Design_Document.md) — earlier design, based on original SOW
- [Telstra_AWS_Agentic_Framework_TAAF_v03_ExecSum_Review.md](../Telstra_AWS_Agentic_Framework_TAAF_v03_ExecSum_Review.md) — current/updated exec summary for the same engagement

---

## What they have in common

| Theme | TAAF (Telstra) | WO-022537 (In-Scope Framework) |
|---|---|---|
| Core idea | Multi-agent, self-service Modernisation framework, reusable across workloads | Multi-tenant, AI-enabled modernization platform, reusable capability |
| Agent roster | Security Agent, DevOps Agent, plus AWS Transform/Claude Code/Kiro for code transformation | DevOps Agent, Security Agent, Modernization Agent, Portfolio Assessment Engine |
| Runtime | Amazon Bedrock AgentCore (multi-tenant), session-isolated microVMs | Amazon Bedrock Agents (recommended default), evaluating LangGraph/CrewAI |
| Human-in-the-loop | Human approval gates in the TAAF flow (design/code review, feedback loop) | Explicit contractual gate — written Engagement Manager approval before any Change (clause 5) |
| Security posture | AU-CRIS, zero data retention, VPC isolation, Cedar policy enforcement, no model training | Non-prod-only boundary, no AWS Information internet-accessible (cl. 4.1), AWS Provider Security Policy compliance (cl. 4.2) |
| Pilot-first delivery | Non-production pilots (VPC→TGW migration, LZ move, runtime upgrade, DevOps/Security pilot) | Single (1) pilot application in non-prod |
| Knowledge transfer | Dedicated KT & Handover phase (weeks 15–16), roadshows, training | Documentation & handover deliverable (implementation guide, runbooks, CCoE model) |

## Key differences

1. **Scale of pilots** — TAAF runs 4 parallel pilot workstreams (network migration, LZ/org move, runtime upgrade, DevOps/Security) vs. WO-022537's single pilot application, end-to-end. TAAF is broader/shallower; WO-022537 is narrower/deeper.
2. **Portfolio-level assessment** — WO-022537 has an explicit **Portfolio Assessment Engine** (§5.4) that categorizes an entire application inventory by complexity/risk/business value. TAAF's deck has no equivalent portfolio-wide assessment component — it's oriented around discrete pathways/agents triggered per request, not a portfolio-wide scoring engine.
3. **Orchestration maturity** — TAAF's deck shows a concrete, already-designed secure deployment architecture (VPC boundary, AgentCore Gateway/Identity/Memory/Policy, PrivateLink, KMS, session isolation) — more architecturally mature/production-ready than WO-022537, which is still evaluating orchestration frameworks (§6.3) and has several open items/assumptions unresolved (foundation model choice, number of blueprints, truncated CCoE/subcontracting clauses).
4. **Deterministic vs. agentic DevOps/Security** — WO-022537 explicitly proposes (§5.6, CBA "Lumos"-informed) a deterministic-first alternative for DevOps/Security (policy-as-code, pipeline-as-execution-layer, AI only for reasoning/summarization) as a lower-risk option. TAAF's deck doesn't surface this distinction — its Security Agent/DevOps Agent are described as more directly agentic (e.g., "Security Agent... iteratively validates," PEN testing agent with "self-adaptive attack chaining"), closer to WO-022537's §5.1/5.2 baseline design than the §5.6 deterministic alternative.
5. **Evidence base** — TAAF cites a real trial (Afterburner Security Agent, 2-week trial, 20 baselines tested, concrete before/after metrics: 2-day SAD, 3.5–7hr PEN tests). WO-022537 has no equivalent trial data yet — it's still a paper design pending the pilot.
6. **Commercial framing** — TAAF: SOW/credits/cost-per-pathway ($250–$550), phased timeline through Sep 2026. WO-022537: fixed capped commercial terms (3,000 hrs, $761,840 AUD, PSA Communities invoicing) — WO-022537 is a tighter, fixed-scope contract vs. TAAF's more open, credit-offset commercial model.
7. **Data residency emphasis** — TAAF explicitly calls out AU-CRIS compliance and Sydney-region-only processing as a first-class design constraint; WO-022537 doesn't mention data residency/sovereignty requirements at this level of specificity.

## Assessment

WO-022537's design is architecturally earlier-stage (open items, orchestration framework undecided, no trial evidence) but has a more rigorous compliance/change-control model (contractual clauses, deterministic-first alternative for high-blast-radius agents) and a portfolio-level assessment capability TAAF lacks. TAAF is further along (concrete AgentCore architecture, real trial data, defined multi-pilot pipeline) but its deck doesn't show the same explicit deterministic-vs-agentic risk analysis that WO-022537's §5.6 provides.

## Recommendations

**Backport into WO-022537's design:**
- TAAF's concrete secure deployment/AgentCore architecture (see TAAF review §12) as a template for WO-022537's still-open orchestration/runtime decision.
- TAAF's Afterburner trial evidence as a proof point to strengthen the WO-022537 Security Agent (§5.2) design confidence.

**Backport into TAAF's approach:**
- WO-022537's Portfolio Assessment Engine concept, since TAAF's pathway-triggered model has no portfolio-wide prioritisation mechanism.
