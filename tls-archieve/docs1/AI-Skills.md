# AI Skills Study Guide — WO-022537 In-Scope Framework

A prioritized learning roadmap for the AI/GenAI aspects of this project. Related docs: [WO-022537_Design_Document.md](WO-022537_Design_Document.md), [WO-022537_Requirements_Summary.md](WO-022537_Requirements_Summary.md).

---

## 1. Amazon Bedrock (foundation — start here)
- Bedrock model catalog (Claude, Nova, Titan) and how to invoke via the Bedrock API/SDK
- **Bedrock Knowledge Bases** — how ingestion, chunking, and retrieval work end-to-end
- **Bedrock Agents** — action groups, tool/function definitions, orchestration traces
- **Bedrock Guardrails** — content filtering, PII redaction, denied topics

*Why:* This is almost certainly the core platform given it's an AWS engagement.

## 2. RAG Fundamentals
- Embeddings — what they are, how similarity search works (cosine similarity, ANN algorithms like HNSW)
- Chunking strategies — fixed-size vs. semantic vs. code-aware chunking (relevant since you'll index both code and docs)
- Retrieval evaluation — precision/recall of retrieved chunks, and how bad retrieval causes hallucination downstream

*Practical exercise:* Build one small RAG pipeline yourself (even locally with a small doc set) to internalize ingestion → embed → store → retrieve → prompt.

## 3. Vector Databases
- Pick 1–2 to go deep on: **OpenSearch Serverless (vector engine)** and **Aurora PostgreSQL + pgvector**
- Understand indexing tradeoffs (HNSW vs. IVF), and how to tune recall vs. latency

## 4. Prompt Engineering
- Structured output prompting (JSON schema enforcement) — critical since agents feed each other's output
- Few-shot examples for classification tasks (portfolio categorization)
- Chain-of-thought prompting for planning/reasoning tasks (migration plans, blueprints)

## 5. Agentic AI / Multi-Agent Systems
- Core concepts: tool-calling/function-calling, ReAct pattern (reason + act loops)
- Multi-agent coordination patterns: supervisor/orchestrator vs. sequential handoff vs. peer-to-peer
- Compare frameworks conceptually: **Bedrock Agents (native)** vs. **LangGraph** vs. **CrewAI** — know when native suffices vs. when you need custom orchestration logic

## 6. AI Guardrails & Safety
- Prompt injection — how it works and how to defend against it (relevant for the Security Agent, which will have real permissions)
- Human-in-the-loop design patterns — how to build approval gates into agent workflows (maps to the contract's Change-approval clause)
- Least-privilege IAM design for agents (an agent should never have more permission than its task requires)

## 7. LLMOps / Observability
- Tracing agent decisions (Bedrock Agent traces, or general LLM observability tools like Langfuse/LangSmith concepts)
- Evaluation pipelines — how teams regression-test prompts/agents before shipping changes
- Cost/latency monitoring per model call

## 8. Application Modernization Domain Knowledge (non-AI but needed to ground the AI outputs)
- The "6 Rs" of migration (rehost, replatform, refactor, re-architect, rebuild, retire)
- Microservices decomposition patterns and API modernization basics
- So you can judge whether the AI's recommendations are actually sound, not just fluent

---

## Suggested Order of Attack
1. Bedrock basics + one hands-on RAG pipeline
2. Bedrock Agents + tool-calling concepts
3. Vector DB deep-dive (pick OpenSearch first, since it's the Bedrock-native default)
4. Guardrails/security — don't skip this, it's contractually significant here
5. Multi-agent orchestration frameworks — compare native vs. LangGraph last, once you understand the fundamentals
