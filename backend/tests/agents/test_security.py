"""Unit tests for the Security Agent (Task 13.3)."""

import inspect

import pytest

from daf.agents.security import SecurityAgent
from daf.agents.validation import validate_output_schema
from daf.models.enums import SpokeResultStatus, TaskType
from daf.models.envelope import TaskEnvelope
from daf.tools.allowlist import AgentRole, McpTool, ToolNotAllowlistedError, enforce_tool_allowlist

import daf.agents.security as security_module


class FakeAwsApiCliClient:
    def __init__(self, findings: list[str]) -> None:
        self._findings = findings
        self.calls: list[str] = []

    def check_iam_policy(self, policy_ref: str) -> list[str]:
        self.calls.append(policy_ref)
        return self._findings


class FakeS3KbClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def retrieve_security_guidance(self, topic: str) -> str:
        self.calls.append(topic)
        return "guidance text"


def _envelope() -> TaskEnvelope:
    return TaskEnvelope(traceId="trace-1", task=TaskType.SECURITY_REVIEW.value, inputs={}, acceptanceCriteria=[])


def test_execute_returns_pass_when_no_findings() -> None:
    aws_client = FakeAwsApiCliClient([])
    kb_client = FakeS3KbClient()
    agent = SecurityAgent(aws_api_cli_client=aws_client, s3_kb_client=kb_client)

    result = validate_output_schema(agent.execute(_envelope(), tier=None), agent.output_schema)

    assert result.status == SpokeResultStatus.SUCCESS
    assert "pass" in result.notes.lower()
    assert aws_client.calls == ["default-policy"]
    assert kb_client.calls == ["iam-policy-review"]


def test_execute_returns_findings_as_success() -> None:
    aws_client = FakeAwsApiCliClient(["finding A", "finding B"])
    kb_client = FakeS3KbClient()
    agent = SecurityAgent(aws_api_cli_client=aws_client, s3_kb_client=kb_client)

    result = validate_output_schema(agent.execute(_envelope(), tier=None), agent.output_schema)

    assert result.status == SpokeResultStatus.SUCCESS
    assert "finding A" in result.notes
    assert "finding B" in result.notes


def test_security_agent_never_gates_the_run() -> None:
    import ast

    tree = ast.parse(inspect.getsource(security_module))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    assert not any(m == "daf.hitl" or m.startswith("daf.hitl.") for m in imported_modules)
    assert not any(m == "daf.models.run" or m.startswith("daf.models.run.") for m in imported_modules)
    assert not hasattr(SecurityAgent, "approve")
    assert not hasattr(SecurityAgent, "block_plan")
    assert not hasattr(SecurityAgent, "reject")
    assert not hasattr(SecurityAgent, "raise_gate")


def test_security_agent_cannot_call_github_tool() -> None:
    with pytest.raises(ToolNotAllowlistedError):
        enforce_tool_allowlist(AgentRole.SECURITY, McpTool.GITHUB)
