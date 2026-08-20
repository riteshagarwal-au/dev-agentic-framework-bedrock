"""Unit tests for the Discovery Agent (Task 13.1)."""

import pytest

from daf.agents.discovery import DiscoveryAgent
from daf.agents.validation import validate_output_schema
from daf.models.common import ArtifactRef
from daf.models.enums import ArtifactKind, ArtifactLocationKind, SpokeResultStatus, TaskType
from daf.models.envelope import SpokeResult, TaskEnvelope
from daf.models.types import TraceId
from daf.tools.allowlist import AgentRole, McpTool, ToolNotAllowlistedError, enforce_tool_allowlist


class FakeAzureMcpClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def list_resources(self, resource_group: str) -> list[dict]:
        self.calls.append(resource_group)
        return [{"id": "res-1", "type": "Microsoft.Compute/virtualMachines"}]


class FakeFilesystemMcpClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def read_file(self, path: str) -> str:
        self.calls.append(path)
        return "fake file contents"


def _envelope(task_type: TaskType, inputs: dict[str, ArtifactRef] | None = None) -> TaskEnvelope:
    return TaskEnvelope(
        trace_id=TraceId("trace-1"),
        task=task_type.value,
        inputs=inputs or {},
        acceptance_criteria=[],
    )


def test_discovery_collect_calls_azure_and_filesystem_and_returns_valid_success_result():
    azure_client = FakeAzureMcpClient()
    filesystem_client = FakeFilesystemMcpClient()
    agent = DiscoveryAgent(
        task_type=TaskType.DISCOVERY_COLLECT,
        azure_mcp_client=azure_client,
        filesystem_mcp_client=filesystem_client,
    )

    result = agent.execute(_envelope(TaskType.DISCOVERY_COLLECT), tier=None)

    validated = validate_output_schema(result, SpokeResult)
    assert validated.status == SpokeResultStatus.SUCCESS
    assert len(azure_client.calls) == 1
    assert len(filesystem_client.calls) == 1


def test_discovery_reason_does_not_call_azure_or_filesystem():
    azure_client = FakeAzureMcpClient()
    filesystem_client = FakeFilesystemMcpClient()
    agent = DiscoveryAgent(
        task_type=TaskType.DISCOVERY_REASON,
        azure_mcp_client=azure_client,
        filesystem_mcp_client=filesystem_client,
    )

    result = agent.execute(_envelope(TaskType.DISCOVERY_REASON), tier=None)

    validated = validate_output_schema(result, SpokeResult)
    assert validated.status == SpokeResultStatus.SUCCESS
    assert len(azure_client.calls) == 0
    assert len(filesystem_client.calls) == 0


def test_discovery_agent_rejects_non_discovery_task_type():
    with pytest.raises(ValueError):
        DiscoveryAgent(
            task_type=TaskType.SECURITY_REVIEW,
            azure_mcp_client=FakeAzureMcpClient(),
            filesystem_mcp_client=FakeFilesystemMcpClient(),
        )


def test_discovery_allowlist_blocks_github():
    with pytest.raises(ToolNotAllowlistedError):
        enforce_tool_allowlist(AgentRole.DISCOVERY, McpTool.GITHUB)
