"""Security Agent (Task 13.3, design.md Component 5 "Security").

The Security Agent's job is strictly to *review* — it calls the AWS API
MCP tool to check IAM policies and the S3 knowledge-base MCP tool for
security guidance, then returns its findings as a `SpokeResult`. It never
approves, blocks, or otherwise gates the run itself: HITL gating (e.g. the
`DESTRUCTIVE_ACTION` gate) is entirely the hook pipeline's/Supervisor's
responsibility, applied *after* this agent returns, based on the returned
`SpokeResult` (Requirement 2.6). Accordingly this module must never import
`daf.hitl` or `daf.models.run` (RunState/RunStatus) — that import boundary
is itself the structural guarantee that this agent cannot self-approve.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from daf.models.common import ArtifactRef, TokenUsage
from daf.models.enums import ArtifactKind, ArtifactLocationKind, SpokeResultStatus, TaskType
from daf.models.envelope import SpokeResult, TaskEnvelope
from daf.models.types import AgentId
from daf.tools.allowlist import AgentRole, McpTool, enforce_tool_allowlist


class AwsApiCliClientProtocol(Protocol):
    def check_iam_policy(self, policy_ref: str) -> list[str]: ...


class S3KbClientProtocol(Protocol):
    def retrieve_security_guidance(self, topic: str) -> str: ...


class ArtifactWriterProtocol(Protocol):
    def write(self, trace_id: str, filename: str, content: str, kind: ArtifactKind, artifact_id: str) -> ArtifactRef: ...


class SecurityAgent:
    """Security spoke agent — see module docstring for the "never gates
    the run" boundary this class must preserve.
    """

    def __init__(
        self,
        aws_api_cli_client: AwsApiCliClientProtocol,
        s3_kb_client: S3KbClientProtocol,
        artifact_writer: ArtifactWriterProtocol | None = None,
    ) -> None:
        self.agent_id: AgentId = AgentId("security")
        self.task_type: TaskType = TaskType.SECURITY_REVIEW
        self.output_schema: type[SpokeResult] = SpokeResult
        self._aws_api_cli_client = aws_api_cli_client
        self._s3_kb_client = s3_kb_client
        self._artifact_writer = artifact_writer

    def execute(self, envelope: TaskEnvelope, tier: Any) -> SpokeResult:
        """Run the IAM-policy check and pull security guidance, and return
        findings as a `SpokeResult`.

        `tier` is accepted but unused: the Deterministic Router (Task 7.x)
        resolves the model tier upstream in the hook pipeline, this agent
        does not need to branch on it.
        """
        policy_ref = envelope.inputs.get("policy")
        policy_ref_str = policy_ref.artifact_id if policy_ref is not None else "default-policy"

        enforce_tool_allowlist(AgentRole.SECURITY, McpTool.AWS_API_CLI)
        findings = self._aws_api_cli_client.check_iam_policy(policy_ref_str)

        enforce_tool_allowlist(AgentRole.SECURITY, McpTool.S3_KB)
        guidance = self._s3_kb_client.retrieve_security_guidance("iam-policy-review")

        if findings:
            notes = f"{len(findings)} finding(s): {'; '.join(findings)}"
        else:
            notes = "PASS: no findings"

        if self._artifact_writer is not None:
            report = {"policyRef": policy_ref_str, "findings": findings, "guidance": guidance}
            output = self._artifact_writer.write(
                trace_id=str(envelope.trace_id),
                filename="security-review.json",
                content=json.dumps(report, indent=2),
                kind=ArtifactKind.OTHER,
                artifact_id=f"security-review-{envelope.trace_id}",
            )
        else:
            output = ArtifactRef(
                artifactId=f"security-review-{envelope.trace_id}",
                location=f"s3://daf-artifacts/security-reviews/{envelope.trace_id}.json",
                locationKind=ArtifactLocationKind.S3_URI,
                kind=ArtifactKind.OTHER,
            )

        return SpokeResult(
            output=output,
            confidence=1.0,
            tokensUsed=TokenUsage(tokensIn=0, tokensOut=0),
            status=SpokeResultStatus.SUCCESS,
            notes=notes,
        )
