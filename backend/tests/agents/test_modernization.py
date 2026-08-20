"""Unit tests for `ModernizationAgent` (Task 13.4)."""

from __future__ import annotations

import pytest

from daf.agents.modernization import ModernizationAgent
from daf.agents.validation import validate_output_schema
from daf.models.enums import SpokeResultStatus, TaskType
from daf.models.envelope import SpokeResult, TaskEnvelope
from daf.tools.allowlist import AgentRole, McpTool, ToolNotAllowlistedError, enforce_tool_allowlist
from tests.supervisor.fakes import FakeAuditLog


class FakeS3KbClient:
    def __init__(self, guidance: str) -> None:
        self._guidance = guidance

    def retrieve_guidance(self, topic: str) -> str:
        return self._guidance


class FakeAwsDocsClient:
    def __init__(self, guidance: str) -> None:
        self._guidance = guidance

    def retrieve_guidance(self, topic: str) -> str:
        return self._guidance


class FakeFilesystemMcpClient:
    def __init__(self) -> None:
        self.read_paths: list[str] = []

    def read_file(self, path: str) -> str:
        self.read_paths.append(path)
        return "{}"


def _envelope() -> TaskEnvelope:
    return TaskEnvelope(
        traceId="trace-1", task=TaskType.MODERNIZATION_PLAN.value, inputs={}, acceptanceCriteria=[]
    )


class TestModernizationAgentExecute:
    def test_matching_guidance_returns_valid_result_without_conflict_notes(self) -> None:
        agent = ModernizationAgent(
            s3_kb_client=FakeS3KbClient("use ECS Fargate"),
            aws_docs_client=FakeAwsDocsClient("use ECS Fargate"),
            filesystem_mcp_client=FakeFilesystemMcpClient(),
            audit_log=FakeAuditLog(),
        )

        result = agent.execute(_envelope(), tier=None)

        validated = validate_output_schema(result, SpokeResult)
        assert validated.status == SpokeResultStatus.SUCCESS
        assert "conflict" not in validated.notes.lower()

    def test_matching_guidance_writes_no_kb_conflict_flagged_audit_event(self) -> None:
        audit_log = FakeAuditLog()
        agent = ModernizationAgent(
            s3_kb_client=FakeS3KbClient("use ECS Fargate"),
            aws_docs_client=FakeAwsDocsClient("use ECS Fargate"),
            filesystem_mcp_client=FakeFilesystemMcpClient(),
            audit_log=audit_log,
        )

        agent.execute(_envelope(), tier=None)

        assert audit_log.events == []

    def test_differing_guidance_notes_mention_both_and_followed_kb(self) -> None:
        agent = ModernizationAgent(
            s3_kb_client=FakeS3KbClient("use ECS Fargate"),
            aws_docs_client=FakeAwsDocsClient("use EKS"),
            filesystem_mcp_client=FakeFilesystemMcpClient(),
            audit_log=FakeAuditLog(),
        )

        result = agent.execute(_envelope(), tier=None)

        assert "use ECS Fargate" in result.notes
        assert "use EKS" in result.notes
        assert "followed" in result.notes.lower()
        assert "kb" in result.notes.lower()

    def test_differing_guidance_writes_exactly_one_kb_conflict_flagged_audit_event(self) -> None:
        audit_log = FakeAuditLog()
        agent = ModernizationAgent(
            s3_kb_client=FakeS3KbClient("use ECS Fargate"),
            aws_docs_client=FakeAwsDocsClient("use EKS"),
            filesystem_mcp_client=FakeFilesystemMcpClient(),
            audit_log=audit_log,
        )

        agent.execute(_envelope(), tier=None)

        conflict_events = [e for e in audit_log.events if e[0] == "kb_conflict_flagged"]
        assert len(conflict_events) == 1
        event, payload = conflict_events[0]
        assert payload["kb_guidance"] == "use ECS Fargate"
        assert payload["aws_docs_guidance"] == "use EKS"
        assert payload["decision"] == "followed_kb"

    def test_modernization_agent_role_is_not_allowlisted_for_github(self) -> None:
        with pytest.raises(ToolNotAllowlistedError):
            enforce_tool_allowlist(AgentRole.MODERNIZATION, McpTool.GITHUB)
