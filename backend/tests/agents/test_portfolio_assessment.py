"""Unit tests for the Portfolio Assessment Agent (Task 13.5)."""

from __future__ import annotations

import pytest

from daf.agents.portfolio_assessment import PortfolioAssessmentAgent
from daf.agents.validation import validate_output_schema
from daf.models.enums import SpokeResultStatus, TaskType
from daf.models.envelope import SpokeResult, TaskEnvelope
from daf.tools.allowlist import AgentRole, McpTool, ToolNotAllowlistedError, enforce_tool_allowlist


class FakeS3KbClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def retrieve_guidance(self, topic: str) -> str:
        self.calls.append(topic)
        return "guidance"


def _make_envelope() -> TaskEnvelope:
    return TaskEnvelope(
        traceId="trace-1",
        task=TaskType.PORTFOLIO_ASSESSMENT.value,
        inputs={},
        acceptanceCriteria=[],
    )


class TestExecute:
    def test_returns_valid_spoke_result_with_categorization_notes(self) -> None:
        fake_client = FakeS3KbClient()
        agent = PortfolioAssessmentAgent(s3_kb_client=fake_client)

        result = agent.execute(_make_envelope(), tier=None)

        validated = validate_output_schema(result, SpokeResult)
        assert validated.status == SpokeResultStatus.SUCCESS
        assert "complexity" in validated.notes
        assert "risk" in validated.notes
        assert "value" in validated.notes
        assert "pathway" in validated.notes
        assert len(fake_client.calls) == 1


class TestAllowlistEnforcement:
    def test_github_is_not_allowlisted(self) -> None:
        with pytest.raises(ToolNotAllowlistedError):
            enforce_tool_allowlist(AgentRole.PORTFOLIO_ASSESSMENT, McpTool.GITHUB)

    def test_aws_api_cli_is_not_allowlisted(self) -> None:
        with pytest.raises(ToolNotAllowlistedError):
            enforce_tool_allowlist(AgentRole.PORTFOLIO_ASSESSMENT, McpTool.AWS_API_CLI)
