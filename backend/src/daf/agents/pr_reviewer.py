"""PR-Reviewer Agent (Task 14.1) — on-demand, advisory-only PR review.

design.md Component 5: the PR-Reviewer is an on-demand agent (distinct
from the 5 core agents' fixed task graph) whose primary tool is "GitHub
MCP (read-only)". Structurally, this agent can never merge/approve/close a
PR itself: `GithubReadOnlyMcpClientProtocol` below only exposes
`get_pull_request_diff` and `post_comment` — no merge/approve/close method
exists anywhere on the protocol or this class, matching the DevOps agent's
established "no code path to a gating action" pattern (Requirement 9.x —
PR-Reviewer is advisory only, HITL/humans decide whether to merge).
"""

from __future__ import annotations

from typing import Any, Protocol

from daf.models.common import ArtifactRef, TokenUsage
from daf.models.enums import ArtifactKind, ArtifactLocationKind, SpokeResultStatus, TaskType
from daf.models.envelope import SpokeResult, TaskEnvelope
from daf.models.types import AgentId
from daf.tools.allowlist import AgentRole, McpTool, enforce_tool_allowlist


class GithubReadOnlyMcpClientProtocol(Protocol):
    """Only `get_pull_request_diff` (read) and `post_comment` (comment)
    are exposed — no merge/approve/close method exists on this protocol,
    so there is no code path through which the PR-Reviewer could gate
    the PR itself.
    """

    def get_pull_request_diff(self, pr_ref: str) -> str: ...

    def post_comment(self, pr_ref: str, body: str) -> str: ...


class PrReviewerAgent:
    """Implements the `SpokeAgentProtocol` shape (duck-typed, per
    `daf.pipeline.pipeline.SpokeAgentProtocol`).
    """

    agent_id: AgentId = AgentId("pr-reviewer")
    task_type: TaskType = TaskType.PR_REVIEW
    output_schema: type[SpokeResult] = SpokeResult

    def __init__(self, github_mcp_client: GithubReadOnlyMcpClientProtocol) -> None:
        self._github_mcp_client = github_mcp_client

    def execute(self, envelope: TaskEnvelope, tier: Any) -> SpokeResult:  # noqa: ARG002 - tier resolved by Router upstream
        pr_artifact = envelope.inputs.get("pull_request")
        pr_ref = pr_artifact.artifact_id if pr_artifact is not None else "unknown-pr"

        enforce_tool_allowlist(AgentRole.PR_REVIEWER, McpTool.GITHUB)
        diff = self._github_mcp_client.get_pull_request_diff(pr_ref)

        # Requirement 9.5: `diff` is untrusted MCP output — it is only ever
        # read as inert text below (e.g. its length), never executed/eval'd
        # and never used to decide which MCP tools to call or to bypass
        # `enforce_tool_allowlist`, so prompt-injection-style content in a
        # PR diff cannot change this agent's behavior.
        risk_score = "LOW"
        diff_summary = f"Diff received ({len(diff)} chars); Phase 1 stub does not run a real LLM review."
        kb_conformance_notes = "no corporate KB guidance available for pre-check in Phase 1 stub"
        focus_list: list[str] = ["Verify diff manually — Phase 1 stub performs no automated analysis."]
        cost_delta = 0.0  # real cost-delta computation is out of scope for this Phase 1 stub

        comment_body = (
            f"PR Review (advisory only)\n"
            f"Risk score: {risk_score}\n"
            f"Summary: {diff_summary}\n"
            f"KB conformance: {kb_conformance_notes}\n"
            f"Focus areas: {'; '.join(focus_list)}\n"
            f"Cost delta: {cost_delta}"
        )
        self._github_mcp_client.post_comment(pr_ref, comment_body)

        output = ArtifactRef(
            artifactId=f"pr-review-{envelope.trace_id}",
            location=f"s3://daf-artifacts/pr-reviews/{envelope.trace_id}.json",
            locationKind=ArtifactLocationKind.S3_URI,
            kind=ArtifactKind.OTHER,
        )

        return SpokeResult(
            output=output,
            confidence=0.5,
            tokensUsed=TokenUsage(tokensIn=0, tokensOut=0),
            status=SpokeResultStatus.SUCCESS,
            notes=(
                f"risk={risk_score}; focus={focus_list}; cost_delta={cost_delta}"
            ),
        )
