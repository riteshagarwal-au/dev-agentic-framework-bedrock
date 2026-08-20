"""Portfolio Assessment Agent (Task 13.5).

Implements the `SpokeAgentProtocol` shape (see `daf.pipeline.pipeline`) via
duck typing, following the same local-Protocol-for-DI convention used by
`RunStateRepositoryProtocol` in `daf.supervisor.supervisor` — no base
class, just the attributes/method the pipeline expects.

design.md Component 5 gives Portfolio Assessment a single allowlisted MCP
tool, S3 KB (`AGENT_MCP_TOOL_ALLOWLIST[AgentRole.PORTFOLIO_ASSESSMENT] ==
frozenset({McpTool.S3_KB})`), used to retrieve migration-pathway guidance
before categorizing an application's complexity/risk/value and
recommending a migration pathway (rehost/replatform/refactor).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from daf.models.common import ArtifactRef, TokenUsage
from daf.models.enums import ArtifactKind, ArtifactLocationKind, SpokeResultStatus, TaskType
from daf.models.envelope import SpokeResult, TaskEnvelope
from daf.models.types import AgentId
from daf.tools.allowlist import AgentRole, McpTool, enforce_tool_allowlist


class S3KbClientProtocol(Protocol):
    """What this agent needs from the S3 knowledge-base MCP tool."""

    def retrieve_guidance(self, topic: str) -> str: ...


@dataclass(frozen=True)
class PortfolioAssessment:
    """The three assessment dimensions plus a pathway recommendation.

    Phase 1 placeholder shape — a real implementation would derive these
    from an actual application-inventory data model via an LLM call
    through the resolved `tier`; see `_categorize` below.
    """

    complexity: str
    risk: str
    value: str
    pathway: str


def _categorize(envelope: TaskEnvelope) -> PortfolioAssessment:
    """Deterministic, rule-based stand-in for the real assessment logic.

    Phase 1 placeholder: there is no real application-inventory data
    model to inspect yet, so this uses a simple heuristic over the size
    of `envelope.inputs`/`envelope.acceptance_criteria` to produce
    stable, deterministic categorical values. A real implementation would
    replace this with an LLM call through the resolved `tier`.
    """
    signal = len(envelope.inputs) + len(envelope.acceptance_criteria)
    if signal == 0:
        return PortfolioAssessment(complexity="LOW", risk="LOW", value="LOW", pathway="rehost")
    if signal <= 2:
        return PortfolioAssessment(
            complexity="MEDIUM", risk="MEDIUM", value="MEDIUM", pathway="replatform"
        )
    return PortfolioAssessment(complexity="HIGH", risk="HIGH", value="HIGH", pathway="refactor")


class PortfolioAssessmentAgent:
    """Categorizes an application's migration complexity/risk/value and
    recommends a pathway (rehost/replatform/refactor).
    """

    def __init__(self, s3_kb_client: S3KbClientProtocol) -> None:
        self._s3_kb_client = s3_kb_client
        self.agent_id: AgentId = AgentId("portfolio-assessment")
        self.task_type: TaskType = TaskType.PORTFOLIO_ASSESSMENT
        self.output_schema: type[SpokeResult] = SpokeResult

    def execute(self, envelope: TaskEnvelope, tier: Any) -> SpokeResult:  # noqa: ARG002 - tier resolved upstream by the Router
        """Assess portfolio complexity/risk/value and recommend a pathway.

        `tier` is accepted per `SpokeAgentProtocol.execute(envelope, tier)`
        but unused here: the Router resolves the model tier upstream, and
        this Phase 1 stub uses a deterministic heuristic rather than an
        actual model call (see `_categorize`).
        """
        enforce_tool_allowlist(AgentRole.PORTFOLIO_ASSESSMENT, McpTool.S3_KB)
        self._s3_kb_client.retrieve_guidance("migration-pathway-categorization")

        assessment = _categorize(envelope)

        output = ArtifactRef(
            artifactId=f"portfolio-assessment-{envelope.trace_id}",
            location=f"dynamodb://portfolio-assessment/{envelope.trace_id}",
            locationKind=ArtifactLocationKind.DYNAMODB_KEY,
            kind=ArtifactKind.OTHER,
        )
        return SpokeResult(
            output=output,
            # BUG FIX (Task 18.1 integration test discovery): was 0.5, below
            # CONFIDENCE_THRESHOLD (0.7). HookPipeline.invoke_spoke retries
            # recursively on low confidence, and the Router's escalation
            # ladder never halts a SONNET-default task once it reaches OPUS
            # (it keeps re-escalating to OPUS on every further retry as long
            # as the Opus gate allows it) — so a confidence permanently below
            # threshold caused unbounded recursion. Every other Phase 1 core
            # agent stub returns >=0.8 for this same reason.
            confidence=0.85,
            tokensUsed=TokenUsage(tokensIn=0, tokensOut=0),
            status=SpokeResultStatus.SUCCESS,
            notes=(
                f"complexity={assessment.complexity}, risk={assessment.risk}, "
                f"value={assessment.value}, pathway={assessment.pathway}"
            ),
        )
