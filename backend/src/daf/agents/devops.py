"""DevOps Agent (Task 13.2) — generates a Terraform plan and opens a PR.

design.md Component 5: DevOps's primary tools are GitHub MCP, Terraform
MCP, and AWS API/CLI MCP. Structurally, this agent can never merge or
apply infrastructure changes itself: `GithubMcpClientProtocol` below only
exposes `open_pull_request` (no merge/approve method exists anywhere on
the protocol or this class), and infra apply is gated by a separate HITL
gate (`HitlGateType.INFRA_APPLY`) enforced upstream in the hook pipeline,
not by this agent.
"""

from __future__ import annotations

from typing import Any, Protocol

from daf.models.common import ArtifactRef, TokenUsage
from daf.models.enums import ArtifactKind, ArtifactLocationKind, SpokeResultStatus, TaskType
from daf.models.envelope import SpokeResult, TaskEnvelope
from daf.models.types import AgentId
from daf.tools.allowlist import AgentRole, McpTool, enforce_tool_allowlist


class TerraformMcpClientProtocol(Protocol):
    def generate_plan(self, blueprint_ref: str) -> str: ...


class GithubMcpClientProtocol(Protocol):
    """Only `open_pull_request` is exposed — no merge/approve method
    exists on this protocol, so there is no code path through which
    DevOps could call one (Requirement re: DevOps never merges/applies).
    """

    def open_pull_request(self, title: str, body: str, branch: str) -> str: ...


class AwsApiCliClientProtocol(Protocol):
    def validate_credentials(self) -> bool: ...


class ArtifactWriterProtocol(Protocol):
    def write(self, trace_id: str, filename: str, content: str, kind: ArtifactKind, artifact_id: str) -> ArtifactRef: ...
    def read_text(self, location: str) -> str: ...


class DevOpsAgent:
    """Implements the `SpokeAgentProtocol` shape (duck-typed, per
    `daf.pipeline.pipeline.SpokeAgentProtocol`).
    """

    agent_id: AgentId = AgentId("devops")
    task_type: TaskType = TaskType.DEVOPS_EXEC
    output_schema: type[SpokeResult] = SpokeResult

    def __init__(
        self,
        terraform_mcp_client: TerraformMcpClientProtocol,
        github_mcp_client: GithubMcpClientProtocol,
        aws_api_cli_client: AwsApiCliClientProtocol,
        artifact_writer: ArtifactWriterProtocol | None = None,
    ) -> None:
        self._terraform_mcp_client = terraform_mcp_client
        self._github_mcp_client = github_mcp_client
        self._aws_api_cli_client = aws_api_cli_client
        self._artifact_writer = artifact_writer

    def execute(self, envelope: TaskEnvelope, tier: Any) -> SpokeResult:  # noqa: ARG002 - tier resolved by Router upstream
        blueprint_ref = envelope.inputs.get("blueprint")
        blueprint_location = blueprint_ref.location if blueprint_ref is not None else "unknown-blueprint"

        enforce_tool_allowlist(AgentRole.DEVOPS, McpTool.TERRAFORM)
        tf_plan = self._terraform_mcp_client.generate_plan(blueprint_location)

        enforce_tool_allowlist(AgentRole.DEVOPS, McpTool.AWS_API_CLI)
        self._aws_api_cli_client.validate_credentials()

        enforce_tool_allowlist(AgentRole.DEVOPS, McpTool.GITHUB)
        pr_url = self._github_mcp_client.open_pull_request(
            title=f"DAF: apply Terraform plan for {envelope.trace_id}",
            body=f"Automated Terraform plan generated from blueprint {blueprint_location!r}.",
            branch=f"daf/{envelope.trace_id}",
        )

        if self._artifact_writer is not None:
            output = self._artifact_writer.write(
                trace_id=str(envelope.trace_id),
                filename="tf-plan.tf",
                content=tf_plan or "# no Terraform plan generated",
                kind=ArtifactKind.TF_PLAN,
                artifact_id=f"tf-plan-{envelope.trace_id}",
            )
        else:
            output = ArtifactRef(
                artifactId=f"tf-plan-{envelope.trace_id}",
                location=f"s3://daf-artifacts/{envelope.trace_id}/tf-plan.json",
                locationKind=ArtifactLocationKind.S3_URI,
                kind=ArtifactKind.TF_PLAN,
            )

        return SpokeResult(
            output=output,
            confidence=0.9,
            tokensUsed=TokenUsage(tokensIn=0, tokensOut=0),
            status=SpokeResultStatus.SUCCESS,
            notes=f"Generated Terraform plan; PR status: {pr_url or 'not created (GITHUB_TOKEN not configured)'}",
        )
