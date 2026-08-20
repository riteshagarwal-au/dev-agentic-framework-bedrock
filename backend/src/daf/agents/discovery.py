"""Discovery Agent (Task 13.1).

design.md Component 5: Discovery collects Azure source-environment
inventory (Haiku tier, `TaskType.DISCOVERY_COLLECT`) and reasons over that
collected inventory (Sonnet tier, `TaskType.DISCOVERY_REASON`). Discovery's
MCP tool allowlist is Azure + Filesystem only (`daf.tools.allowlist`).

This class implements the `SpokeAgentProtocol` shape used by
`daf.pipeline.pipeline.HookPipeline` (duck-typed, no ABC — matching the
`RunStateRepositoryProtocol`-style Protocol pattern used elsewhere in this
codebase) rather than subclassing `daf.agents.base.SpokeAgent`.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from daf.models.common import ArtifactRef, TokenUsage
from daf.models.enums import ArtifactKind, ArtifactLocationKind, SpokeResultStatus, TaskType
from daf.models.envelope import SpokeResult, TaskEnvelope
from daf.models.types import AgentId
from daf.tools.allowlist import AgentRole, McpTool, enforce_tool_allowlist

_DISCOVERY_TASK_TYPES = frozenset({TaskType.DISCOVERY_COLLECT, TaskType.DISCOVERY_REASON})


class AzureMcpClientProtocol(Protocol):
    """Minimal Phase 1 stub-level Azure MCP client interface Discovery needs."""

    def list_resources(self, resource_group: str) -> list[dict]: ...


class FilesystemMcpClientProtocol(Protocol):
    """Minimal Phase 1 stub-level Filesystem MCP client interface Discovery needs."""

    def read_file(self, path: str) -> str: ...


class DiscoveryAgent:
    """Discovery spoke agent — collects (Haiku) or reasons over (Sonnet)
    Azure source-environment inventory.

    One instance handles either `DISCOVERY_COLLECT` or `DISCOVERY_REASON`;
    `agent_id` is a fixed constant (`"discovery"`) because both task
    categories belong to the same logical Discovery agent (design.md
    Component 5), not two distinct agents.
    """

    output_schema: type[SpokeResult] = SpokeResult

    def __init__(
        self,
        task_type: TaskType,
        azure_mcp_client: AzureMcpClientProtocol,
        filesystem_mcp_client: FilesystemMcpClientProtocol,
    ) -> None:
        if task_type not in _DISCOVERY_TASK_TYPES:
            raise ValueError(
                f"DiscoveryAgent only supports {sorted(t.value for t in _DISCOVERY_TASK_TYPES)}, got {task_type!r}"
            )
        self.task_type = task_type
        self.agent_id: AgentId = AgentId("discovery")
        self._azure_mcp_client = azure_mcp_client
        self._filesystem_mcp_client = filesystem_mcp_client

    def execute(self, envelope: TaskEnvelope, tier: Any) -> SpokeResult:
        # `tier` is the Router's already-resolved ModelTier; Phase 1 stub
        # does not yet make a real Bedrock model-invocation call with it.
        del tier
        if self.task_type == TaskType.DISCOVERY_COLLECT:
            return self._collect(envelope)
        return self._reason(envelope)

    def _collect(self, envelope: TaskEnvelope) -> SpokeResult:
        enforce_tool_allowlist(AgentRole.DISCOVERY, McpTool.AZURE)
        resource_group = envelope.inputs.get("resourceGroup")
        resource_group_name = resource_group.location if resource_group else "unknown-resource-group"
        self._azure_mcp_client.list_resources(resource_group_name)

        enforce_tool_allowlist(AgentRole.DISCOVERY, McpTool.FILESYSTEM)
        source_tree = envelope.inputs.get("sourceTree")
        source_path = source_tree.location if source_tree else "unknown-path"
        self._filesystem_mcp_client.read_file(source_path)

        output = ArtifactRef(
            artifact_id=str(uuid.uuid4()),
            location=f"s3://daf-artifacts/{envelope.trace_id}/inventory.json",
            location_kind=ArtifactLocationKind.S3_URI,
            kind=ArtifactKind.INVENTORY,
        )
        return SpokeResult(
            output=output,
            confidence=0.9,
            tokens_used=TokenUsage(tokens_in=400, tokens_out=150),
            status=SpokeResultStatus.SUCCESS,
            notes="Collected Azure resource inventory via Azure and Filesystem MCP tools.",
        )

    def _reason(self, envelope: TaskEnvelope) -> SpokeResult:
        # Reasoning operates over inventory already collected by a prior
        # DISCOVERY_COLLECT step (passed via envelope.inputs) — no fresh
        # Azure/Filesystem MCP tool call is made here.
        output = ArtifactRef(
            artifact_id=str(uuid.uuid4()),
            location=f"s3://daf-artifacts/{envelope.trace_id}/inventory-findings.json",
            location_kind=ArtifactLocationKind.S3_URI,
            kind=ArtifactKind.OTHER,
        )
        return SpokeResult(
            output=output,
            confidence=0.85,
            tokens_used=TokenUsage(tokens_in=1200, tokens_out=400),
            status=SpokeResultStatus.SUCCESS,
            notes="Reasoned over collected inventory to produce discovery findings.",
        )
