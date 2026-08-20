# Discovery Questionnaire — WO-022537 In-Scope Framework

Questions to clarify with the Client (AWS) and/or Customer stakeholders before/during solution design. Grouped by theme. Related docs: [WO-022537_Design_Document.md](WO-022537_Design_Document.md), [WO-022537_Requirements_Summary.md](WO-022537_Requirements_Summary.md), [AI Assisted Migration Framework.md](AI%20Assisted%20Migration%20Framework.md).

---

## 1. Scope & Contract Clarifications

- The source contract text is truncated in a few places — can we get the full, unredacted Work Order text for:
  - The CCoE operating model deliverable description (cut off mid-sentence)
  - Clause 4.3(a) — subcontracting/delegation restrictions
  - The opening scope paragraph (starts mid-sentence: "...operational processes designed to establish modernization requirements")
- How many target-state blueprints does AWS/Customer expect to mutually agree on? Is there a rough number in mind, or is this fully open-ended?
- Is the "one (1) application" pilot already identified, or do we need to help select it? If not yet selected, what criteria should we use (complexity, business criticality, representativeness)?
- Is this Work Order intended to be a one-off pilot, or the first phase of a longer multi-phase program (i.e., should we design for future scale-out beyond the pilot)?

## 2. Customer / Business Context

- Who is the end Customer (the organization actually receiving this framework), and who are the key stakeholders/sponsors on their side?
- What industry/regulatory context does the Customer operate in (e.g., finance, healthcare, government)? Are there specific compliance regimes (PCI-DSS, HIPAA, APRA, IRAP, etc.) we must design for?
- What are the Customer's primary modernization drivers — cost reduction, technical debt, agility, M&A integration, EOL/EOS pressure, regulatory mandate?
- Does the Customer have existing modernization or migration initiatives underway that this framework needs to integrate with or avoid duplicating?

## 3. Application Portfolio & Use Cases

- What is the size/shape of the Customer's application portfolio (rough count, tech stack diversity, on-prem vs. cloud today)?
- What specific use cases has the Customer selected/prioritized (per the SOW's "Customer-selected use cases and modernization priorities")? Can we get that list?
- What is the current state architecture and platform this pilot application runs on (on-prem, other cloud, legacy AWS account, etc.)?
- Are there existing CMDB, architecture docs, or code repositories we'll get access to for discovery/RAG ingestion, or do we need to build the inventory from scratch?

## 4. Multi-Tenant Platform Requirements

- Who are the "tenants" in the multi-tenant platform — different business units, different applications, or different Customer sub-entities?
- What level of tenant isolation is required (logical separation via IAM/tagging vs. full infrastructure separation per tenant)?
- Are there existing multi-tenant patterns or platforms at AWS/Customer we should align with, or is this greenfield?

## 5. AI/Technology Preferences & Constraints

- Is Amazon Bedrock the assumed/mandated AI platform, or is model/platform choice open?
- Are there approved/preferred foundation models already vetted by Customer's security team?
- Does the Customer have data residency requirements that affect model hosting region or data storage location?
- Is there an existing enterprise AI governance policy (e.g., approved AI tools list, prompt logging requirements) we need to comply with?
- Any restrictions on using third-party orchestration frameworks (LangChain/LangGraph/CrewAI) vs. requiring AWS-native tooling only?
- Does the Customer have existing vector databases, search infrastructure, or data platforms we should reuse rather than standing up new ones?

## 6. Security, Compliance & Guardrails

- What exactly does the AWS Provider Security Policy require in practice — can we get a walkthrough or checklist, not just the linked policy page?
- What are the boundaries of "non-production environment" here — is there a shared non-prod, or a dedicated environment for this engagement?
- Who has authority to approve "Changes" under clause 5 — is there a single named Engagement Manager, or a change board?
- What existing IAM/account structure exists that the agents will operate within (dedicated AWS account, shared account, service control policies)?
- Are there specific guardrails required for autonomous agent actions (e.g., no agent may modify production, no agent may create new IAM roles, etc.)?

## 7. Data Access & Discovery Inputs

- What documentation, code repos, and architecture artifacts will be made available for the Discover/Assess phases, and how (direct repo access, exported docs, workshops)?
- Are there subject-matter experts (app owners, platform engineers) available for interviews/workshops during Discover?
- Is there existing dependency-mapping tooling (e.g., AWS Application Discovery Service, CMDB) already in place we should ingest from?

## 8. CCoE / Governance

- Does the Customer already have a Cloud Center of Excellence, or are we establishing one from scratch?
- Who are the intended owners/operators of the CCoE operating model post-handover?
- What existing governance processes (change management, architecture review boards) need to be integrated with vs. replaced?

## 9. Success Criteria & Measurement

- How will success of the pilot be measured — time saved, cost reduction, defect rate, stakeholder satisfaction?
- Is there an expectation this becomes a reusable capability across other Customer applications/AWS engagements, or is it scoped strictly to this one Work Order?
- What does "done" look like for AWS at the end of this Work Order — signed-off deliverables only, or a working demo/live pilot?

## 10. Team, Timeline & Delivery Constraints

- Are there fixed milestone dates (beyond the $761,840 / 3,000-hour cap) that we need to plan against?
- Who from Versent and Customer/AWS forms the core working group for ongoing decisions?
- Are there dependencies on other AWS or Customer teams/projects that could block our timeline?

---

## Suggested Next Steps
- [ ] Schedule discovery workshop(s) with AWS Engagement Manager + Customer stakeholders
- [ ] Request full/unredacted Work Order document to resolve open contractual questions (Section 1)
- [ ] Confirm pilot application selection criteria and shortlist
- [ ] Request access to existing architecture docs, CMDB, and code repositories
- [ ] Clarify AI platform/tooling constraints before finalizing technical design
