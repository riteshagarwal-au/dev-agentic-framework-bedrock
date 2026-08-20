"""Unit tests for the DevOps Agent (Task 13.2)."""

import pytest

from daf.agents.devops import DevOpsAgent, GithubMcpClientProtocol
from daf.agents.validation import validate_output_schema
from daf.models.enums import SpokeResultStatus, TaskType
from daf.models.envelope import SpokeResult, TaskEnvelope
from daf.tools.allowlist import AgentRole, McpTool, ToolNotAllowlistedError, enforce_tool_allowlist


class FakeTerraformMcpClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def generate_plan(self, blueprint_ref: str) -> str:
        self.calls.append(blueprint_ref)
        return "s3://plans/plan.json"


class FakeGithubMcpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def open_pull_request(self, title: str, body: str, branch: str) -> str:
        self.calls.append((title, body, branch))
        return "https://github.com/example/repo/pull/1"


class FakeAwsApiCliClient:
    def __init__(self) -> None:
        self.call_count = 0

    def validate_credentials(self) -> bool:
        self.call_count += 1
        return True


def _make_envelope() -> TaskEnvelope:
    return TaskEnvelope(traceId="trace-1", task=TaskType.DEVOPS_EXEC.value, inputs={}, acceptanceCriteria=[])


def test_execute_returns_valid_spoke_result() -> None:
    terraform_client = FakeTerraformMcpClient()
    github_client = FakeGithubMcpClient()
    aws_client = FakeAwsApiCliClient()
    agent = DevOpsAgent(
        terraform_mcp_client=terraform_client,
        github_mcp_client=github_client,
        aws_api_cli_client=aws_client,
    )

    result = agent.execute(_make_envelope(), tier=None)

    validated = validate_output_schema(result, SpokeResult)
    assert validated.status == SpokeResultStatus.SUCCESS
    assert len(github_client.calls) == 1


def test_github_protocol_has_no_merge_or_approve_method() -> None:
    fake_github_client = FakeGithubMcpClient()
    assert not hasattr(fake_github_client, "merge_pull_request")
    assert not hasattr(fake_github_client, "approve_pull_request")

    protocol_members = {
        name
        for name in vars(GithubMcpClientProtocol)
        if not name.startswith("_")
    }
    assert protocol_members == {"open_pull_request"}


def test_enforce_tool_allowlist_rejects_tool_not_in_devops_allowlist() -> None:
    with pytest.raises(ToolNotAllowlistedError):
        enforce_tool_allowlist(AgentRole.DEVOPS, McpTool.AZURE)
