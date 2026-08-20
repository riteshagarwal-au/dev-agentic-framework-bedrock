# CBA / AWS ProServe Agentic Modernization Case Study ("Lumos")

**Source:** AWS re:Invent 2025 session — Dinad (Head of Modernization, AWS ProServe ANZ) and Ash Mullen (GM Cloud Acceleration, Commonwealth Bank of Australia / acting CTO CBA India).
**Topic:** How CBA and AWS ProServe built an agentic AI modernization platform ("Lumos") to accelerate legacy application migration/modernization at scale.

Related docs: [WO-022537_Design_Document.md](WO-022537_Design_Document.md), [WO-022537_Requirements_Summary.md](WO-022537_Requirements_Summary.md), [AI-Skills.md](AI-Skills.md), [Discovery.md](Discovery.md).

---

## 1. The Problem CBA Faced

- ~370 applications assessed for cloud migration, many built 10–15+ years ago
- Knowledge loss: original developers gone, documentation scattered across multiple past projects ("documentation archaeology")
- Huge technical debt: outdated packages, lost build artifacts, no automated tests
- Baseline velocity before AI: **~10 applications/year**
- After introducing agentic AI: **~20–30 applications/quarter** — a major uptick in velocity

## 2. Industry Context (from the talk)

- ~70% of enterprise workloads still on-prem; average code age 20+ years
- Average enterprise transformation takes 1–2 years
- Three transformation types: infrastructure migration, application modernization, risk remediation
- Common challenges: slow/manual processes, limited scalability of monolith changes, scarcity of expertise (skills gap between infra and app modernization)

## 3. Evolution of Agentic AI Patterns (Dinad's framework)

1. **Content generation** — simple prompt → output (code, image, text)
2. **ReAct agents** — reasoning + breaking tasks into steps
3. **Fully autonomous multi-agent systems** — dynamic, multi-step workflows in changing environments

### Agent pattern taxonomy presented
- **Basic reasoning agent** — no tools/memory, pure context reasoning (e.g., interpreting a policy/licensing doc)
- **Tool-based agent** — bridges thinking and doing; calls APIs/Lambdas/DB queries (e.g., code modernization agent calling compliance APIs)
- **Memory-augmented agents** — short-term memory (recent commits/peer review feedback) and long-term memory (cross-session standards like API/APRA compliance)
- **Multi-agent workflow orchestration** — an orchestrator coordinating discovery → refactor → test → compliance-doc agents

## 4. CBA's Platform: "Lumos"

Three-stage structure:
1. **Analyze and Design**
2. **Transform and Test**
3. **Deploy and Operate**

### Analyze & Design details
- Records application-owner interviews (transcripts) anchored to CMDB application ID
- Extracts requirements as user stories in Gherkin format for engineering backlog
- Network/dependency analysis via VMware NSX API integration → visual flow diagrams
- Code analysis: tech stack detection, functionality breakdown, API endpoints, DB libraries
- Cloud readiness assessment: critical issues (security/compliance), version upgrade recommendations, dependency matrix, class + sequence diagrams
- **Solution document + cyber security position generation** via a **content-writer agent + content-reviewer agent loop** — writer drafts, reviewer scores (e.g., 30% → feedback → revise, up to 3 iterations) until quality threshold met
- Human can give inline feedback to dynamically update generated docs
- Output exported as Markdown directly into the codebase

### Transform & Test details
- Automated code modernization: tries **OpenRewrite** first (deterministic), falls back to **Amazon Q Developer / Q CLI** (AI) if OpenRewrite fails or produces poor quality
- Iterates build → test → fix until successful; raises a **pull request** for human review
- **Confidence scoring** on AI changes (lines changed, files touched, libraries modified) — low confidence triggers "try again, touch less"
- Legacy SQL Server (2012 → 2019, and 2012 → AWS Glue cloud-native) modernization accelerator using Bedrock analysis + AWS Schema Conversion Tool
- UI/E2E test generation: AI writes Selenium scripts from a natural-language prompt describing test intent; captures screenshots as test evidence

### Deploy & Operate details
- Internal "DevOps Hosting Platform" (DHP) — simplified IaC parameters instead of hand-written Terraform/CloudFormation
- Built-in guardrail validation (e.g., blocks internet-facing EC2 instances)
- Push-button deployment: PR generated → GitHub Actions → infrastructure provisioned + app deployed

## 5. Underlying Technical Architecture

- **Frontend:** Next.js container on ECS/Fargate
- **Orchestrator agent** running on **Agent Core** runtime
- **Agentic framework:** Pydantic AI (also mentioned: LangChain, Strands as alternatives)
- **Model platform:** Amazon Bedrock
- **Vector store:** **OpenSearch Serverless**
- **Knowledge base:** AWS Knowledge Base RAG backed by S3
- **Integration:** existing internal **MCP (Model Context Protocol) servers** at CBA for compliance/enterprise data
- **Reliability approach:** deterministic engines (static code analyzers, OpenRewrite) provide verified "facts"; AI provides "intelligence" on top — reduces hallucination, increases auditability

## 6. Key Lessons/Challenges Shared

- Large repo analysis broke LLM context windows repeatedly — solved by decomposing repos via Step Functions + Lambda into smaller chunks, then reassembling
- Point accelerators alone weren't enough — customers wanted full end-to-end code-transform outcomes, not isolated tools → led to building "modernization pathways" (opinionated end-to-end workflows)
- Future roadmap: continuous/self-triggering agents (agent-initiated modernization vs. human-triggered), cross-repo dependency analysis, self-improving agents, broader language coverage (.NET, Java, Node.js, iOS, Android), self-updating documentation as code evolves

---

## 7. How This Applies to Our Project (WO-022537 / Telstra)

This is essentially a **proven, production-validated version of what we're designing** — strong external validation for our approach, plus concrete implementation patterns we can borrow.

### Direct parallels to our WO-022537 design

| Our Design Doc | CBA/Lumos (this transcript) | Match |
|---|---|---|
| Multi-agent architecture (DevOps, Security, Modernization, Portfolio agents + orchestrator) | Orchestrator agent coordinating content-writer, reviewer, code-analysis, discovery, refactor, test agents | Near-identical pattern |
| Amazon Bedrock as foundation model platform | Explicitly uses **Bedrock** models | Exact match |
| RAG / Knowledge Base for grounding | **AWS Knowledge Base RAG in S3**, exact same concept as our Section 6.2 | Exact match |
| OpenSearch Serverless as vector store (our recommended default) | **"Our MCP server and AI agents uses OpenSearch Serverless as our vector store"** | Exact match — validates our recommendation directly |
| LangChain/LangGraph/CrewAI as orchestration options | Uses **Pydantic AI** as their orchestration framework (LangChain/Strands/CrewAI considered as alternatives) | Same category of choice we flagged |
| Model Context Protocol (MCP) mentioned in our AI-Skills notes as adjacent concept | Explicitly uses **MCP servers** to connect to CBA-internal systems/compliance data | Same technology, validates it's a real pattern to know |
| Human-in-the-loop / approval gates (our Change-approval clause 5) | Explicit human-in-the-loop PR review before merging AI-generated code | Exact match |
| Guardrails/security scanning (our Security Agent) | Built-in validation rules (e.g., blocks internet-facing EC2), continuous compliance agent | Exact match |
| Portfolio Assessment Engine (AI categorization, pathway recommendation) | Code analysis → cloud readiness assessment → critical issues → modernization pathway | Exact match |
| CCoE / governance documentation deliverable | Deterministic + AI engine combo for auditability/reliability, compliance doc generation | Conceptually matches |
| One (1) pilot application | Demo scoped to "sample application" (a real, renamed CBA app) as proof point before scaling | Same pattern — pilot first, then scale |
| Target-state blueprints / architecture diagrams | Auto-generated solution documents, cyber security position docs, class/sequence diagrams | Exact match |

### Direct validation of our design choices
- Our recommendation of **Bedrock + OpenSearch Serverless + Knowledge Bases for RAG** matches CBA's actual production stack exactly.
- Our multi-agent architecture (DevOps / Security / Modernization / Portfolio Assessment agents + orchestrator) mirrors CBA's orchestrator + discovery/refactor/test/compliance-agent pattern.
- Our emphasis on human-in-the-loop approval (tied to WO-022537 clause 5, Change approval) matches CBA's mandatory PR review step before any AI-generated code is merged.
- Our Security Agent concept (policy/compliance checks, exposure scanning) matches CBA's built-in deployment guardrails (e.g., blocking internet-facing resources) — directly relevant to our contract's clause 4.1 (no AWS Information internet-accessible).

### Concrete patterns to adopt/adapt for our project
1. **Deterministic + AI pairing** — pair AI agents with deterministic tools (static analyzers, schema conversion tools, linters) rather than relying on AI alone for code changes. Reduces hallucination risk and increases auditability — important for a client-facing engagement like Telstra's where trust/reliability matters.
2. **Writer/Reviewer agent loop** — use a two-agent (generator + critic) pattern with iterative scoring for our documentation deliverables (implementation guide, architecture diagrams, CCoE docs) to improve output quality without heavy manual rework.
3. **Confidence scoring on agent-generated changes** — quantify risk of AI changes (files touched, lines changed) before human review, to prioritize reviewer attention and catch overreach early.
4. **MCP servers for enterprise integration** — if Telstra (or the relevant Customer) has internal systems (CMDB, compliance databases), use MCP as the standard integration mechanism rather than bespoke API calls per agent — more maintainable and reusable.
5. **Chunking large repos via serverless orchestration** — anticipate context-window limits early; plan a repo-decomposition strategy (e.g., Step Functions + Lambda) rather than discovering this issue mid-delivery.
6. **Add a dedicated Testing/Validation Agent** — our current design didn't include one explicitly; CBA's Selenium/computer-use test generation agent is a good addition, especially for legacy apps with no existing test coverage (a near-certainty for older Telstra/Customer applications).
7. **Pilot-first, pathway-later approach** — CBA validated on one real (renamed) sample application before building broader "modernization pathways." This matches our SOW's one (1) pilot application requirement — a good, low-risk way to prove the framework before scaling.
8. **Track "job done" vs. "future value"** — CBA explicitly called out the trap of treating delivery as complete once the pilot works; plan from the start for continuous/self-updating documentation and self-improving agents as an explicit backlog item, not an afterthought.

### Suggested next step
Update [WO-022537_Design_Document.md](WO-022537_Design_Document.md) to incorporate: (a) the deterministic-engine pairing principle, (b) the writer/reviewer agent pattern for documentation generation, (c) confidence scoring on DevOps Agent changes, (d) MCP as the integration standard, and (e) a new Testing/Validation Agent alongside the existing four agents.
