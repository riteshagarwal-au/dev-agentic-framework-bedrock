# BNZ Prep Checklist — Loan Document AI Verification Agent

**Kick-off:** Monday | **Discovery/Problem Workshop due:** 2026-08-07 | **Prototype due:** 2026-09-18

Related: [BNZ - Versent - AWS Work Order.md](BNZ%20-%20Versent%20-%20AWS%20Work%20Order.md)

---

## Priority 1 — Must-know before Monday

- [ ] **Amazon Bedrock basics** — model catalog (Claude, Nova, Titan), invoking models via console/API/SDK
- [ ] **Bedrock AgentCore** — action groups, tool/function calling, session & memory handling, agent orchestration traces *(named explicitly in the SOW — do not skip)*
- [ ] **RAG fundamentals** — embeddings, chunking, retrieval basics; likely needed for "information gathering" from loan documents
- [ ] **AWS Prototyping engagement model** — understand the process: Problem Workshop → Solution Space document → Prototype → Path to Production, so you're not learning the process live in the workshop

## Priority 2 — Useful within week 1

- [ ] **Document AI / IDP on AWS** — Amazon Textract, Bedrock Data Automation (directly relevant to loan document verification)
- [ ] **Human-in-the-loop design patterns** — SOW explicitly requires "human in the loop interactions" in the prototype
- [ ] **Explainability for verification outputs** — SOW emphasizes "accurate and explainable" outputs; look into how Bedrock/agent traces can be surfaced for auditability (high compliance sensitivity — it's a bank)

## Priority 3 — Nice to have, can learn during the engagement

- [ ] Conversational interface patterns (one of the three experimentation dimensions named in the SOW)
- [ ] Cost/security write-up patterns — skim a Well-Architected-style cost/security review, since the "Path to Production" deliverable requires this

## Suggested Time Allocation (before Monday)

| Time | Focus |
|---|---|
| 1–2 hrs | Bedrock + AgentCore docs/tutorials (hands-on if possible — spin up a trivial agent) |
| 1 hr | AWS Prototyping engagement methodology overview |
| 1 hr | Textract / Bedrock Data Automation basics |
| 30 min | Human-in-the-loop + explainability patterns for regulated industries |

## Workshop-Day Reminders

- Milestone 1 (Discovery & Problem Definition) and Milestone 2 (Solution Design & Experimentation) share the **same due date (2026-08-07)** — be ready to move fast from problem alignment straight into solution exploration.
- Three named experimentation dimensions to probe in the workshop: **information gathering**, **decision-making**, **conversational interface capabilities**.
- Contract requires: written EM approval before any Change, non-prod/no-internet-access testing environment, AWS-led peer review (code + security + business impact) before Changes.
- All Deliverables go to the **AWS Engagement Manager only** — never submit directly to the Customer (BNZ).
