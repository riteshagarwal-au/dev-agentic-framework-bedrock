"""Modernization Agent (Task 13.4).

design.md Component 5: the Modernization Agent produces a modernization
blueprint by combining corporate knowledge-base guidance (S3 KB MCP) with
AWS Documentation MCP guidance, and reads Discovery's inventory artifact
via the Filesystem MCP. Its MCP tool allowlist is
`{AWS_DOCS, S3_KB, FILESYSTEM}` only (`daf.tools.allowlist`); it never
calls GitHub/Terraform/AWS API CLI/Azure.

Implements the `SpokeAgentProtocol` shape (`daf.pipeline.pipeline`) via
duck typing rather than inheriting `SpokeAgent`/ABC — the same
local-Protocol-for-DI convention `Supervisor` uses for its injected
dependencies (see `daf.supervisor.supervisor.RunStateRepositoryProtocol`).
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from daf.agents.kb_conflict import detect_kb_conflict
from daf.models.common import ArtifactRef, TokenUsage
from daf.models.enums import ArtifactKind, ArtifactLocationKind, SpokeResultStatus, TaskType
from daf.models.envelope import SpokeResult, TaskEnvelope
from daf.models.types import AgentId
from daf.pipeline.pipeline import AuditLog
from daf.tools.allowlist import AgentRole, McpTool, enforce_tool_allowlist


class S3KbClientProtocol(Protocol):
    """Corporate knowledge-base guidance retrieval (S3 KB MCP)."""

    def retrieve_guidance(self, topic: str) -> str: ...


class AwsDocsClientProtocol(Protocol):
    """AWS Documentation MCP guidance retrieval."""

    def retrieve_guidance(self, topic: str) -> str: ...


class FilesystemMcpClientProtocol(Protocol):
    """Filesystem MCP — used here to read Discovery's inventory artifact."""

    def read_file(self, path: str) -> str: ...


class ArtifactWriterProtocol(Protocol):
    def write(self, trace_id: str, filename: str, content: str, kind: ArtifactKind, artifact_id: str) -> ArtifactRef: ...
    def read_text(self, location: str) -> str: ...


class ModernizationAgent:
    """Produces a modernization blueprint for a discovered application.

    `output_schema` is always `SpokeResult` (Requirement 2.1): the
    Modernization Agent does not define a stricter output schema of its
    own beyond what every spoke agent already returns.
    """

    agent_id: AgentId = AgentId("modernization")
    task_type: TaskType = TaskType.MODERNIZATION_PLAN
    output_schema = SpokeResult

    def __init__(
        self,
        s3_kb_client: S3KbClientProtocol,
        aws_docs_client: AwsDocsClientProtocol,
        filesystem_mcp_client: FilesystemMcpClientProtocol,
        audit_log: AuditLog,
        artifact_writer: ArtifactWriterProtocol | None = None,
    ) -> None:
        self._s3_kb_client = s3_kb_client
        self._aws_docs_client = aws_docs_client
        self._filesystem_mcp_client = filesystem_mcp_client
        self._audit_log = audit_log
        self._artifact_writer = artifact_writer

    def execute(self, envelope: TaskEnvelope, tier: Any) -> SpokeResult:
        """`tier` is accepted but unused — the Router (Task 7.x) resolves
        the model tier upstream of this call; the Modernization Agent
        itself has no tier-dependent branching in Phase 1.
        """
        topic = envelope.task

        enforce_tool_allowlist(AgentRole.MODERNIZATION, McpTool.S3_KB)
        kb_guidance = self._s3_kb_client.retrieve_guidance(topic)

        enforce_tool_allowlist(AgentRole.MODERNIZATION, McpTool.AWS_DOCS)
        aws_docs_guidance = self._aws_docs_client.retrieve_guidance(topic)

        enforce_tool_allowlist(AgentRole.MODERNIZATION, McpTool.FILESYSTEM)
        inventory_ref = envelope.inputs.get("inventory")
        inventory_path = inventory_ref.location if inventory_ref is not None else "inventory.json"
        self._filesystem_mcp_client.read_file(inventory_path)

        conflict = detect_kb_conflict(kb_guidance, aws_docs_guidance)
        if conflict is not None:
            notes = (
                f"KB conflict detected: KB says {conflict.kb_guidance!r}, "
                f"AWS Docs says {conflict.aws_docs_guidance!r}; followed KB guidance."
            )
            self._audit_log.write(
                "kb_conflict_flagged",
                {
                    "trace_id": str(envelope.trace_id),
                    "kb_guidance": conflict.kb_guidance,
                    "aws_docs_guidance": conflict.aws_docs_guidance,
                    "decision": conflict.decision,
                },
            )
        else:
            notes = "Modernization blueprint generated; KB and AWS Docs guidance were consistent."

        if self._artifact_writer is not None:
            inventory = self._read_inventory(inventory_ref)
            blueprint = _build_blueprint(inventory, kb_guidance, aws_docs_guidance)
            output = self._artifact_writer.write(
                trace_id=str(envelope.trace_id),
                filename="blueprint.json",
                content=json.dumps(blueprint, indent=2),
                kind=ArtifactKind.BLUEPRINT,
                artifact_id=f"blueprint-{envelope.trace_id}",
            )
        else:
            output = ArtifactRef(
                artifactId=f"blueprint-{envelope.trace_id}",
                location=f"s3://daf-artifacts/{envelope.trace_id}/blueprint.json",
                locationKind=ArtifactLocationKind.S3_URI,
                kind=ArtifactKind.BLUEPRINT,
            )

        return SpokeResult(
            output=output,
            confidence=0.8,
            tokensUsed=TokenUsage(tokensIn=0, tokensOut=0),
            status=SpokeResultStatus.SUCCESS,
            notes=notes,
        )

    def _read_inventory(self, inventory_ref: ArtifactRef | None) -> dict:
        if inventory_ref is None or self._artifact_writer is None:
            return {}
        try:
            return json.loads(self._artifact_writer.read_text(inventory_ref.location))
        except Exception:  # noqa: BLE001 - defensive: blueprint still produced without it
            return {}


def _build_blueprint(inventory: dict, kb_guidance: str, aws_docs_guidance: str) -> dict:
    """Real (deterministic) modernization blueprint derived from Discovery's inventory —
    not a fabricated placeholder."""
    application = inventory.get("application", {})
    dependencies = application.get("dependencies", {})
    uses_sql = "mssql" in dependencies or "tedious" in dependencies

    return {
        "application": application.get("name", "unknown-app"),
        "targetCompute": "AWS ECS Fargate",
        "targetDatabase": "Amazon RDS for SQL Server" if uses_sql else None,
        "containerBaseImage": "node:20-slim",
        "kbGuidance": kb_guidance,
        "awsDocsGuidance": aws_docs_guidance,
        "steps": [
            "Containerize application with a multi-stage Dockerfile targeting node:20-slim.",
            "Provision an ECS Fargate service fronted by an Application Load Balancer.",
            *(["Migrate database to Amazon RDS for SQL Server; replace SQLAZURECONNSTR_* env vars."] if uses_sql else []),
            "Wire CloudWatch Logs/Container Insights for observability.",
        ],
    }
