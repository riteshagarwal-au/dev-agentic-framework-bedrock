"""Per-agent MCP tool allowlist configuration and enforcement (Task 4.2).

design.md Algorithm 4 "Pre/Post Agent-Invocation Hook Pipeline":

    attachGuardrails(envelope)
    attachCachedSystemPrompt(agent)              // prompt caching, source §5.5/§6.4
    enforceToolAllowlist(agent)                   // source §12.4

design.md "Security Considerations":
    "MCP tool calls are allowlisted per agent role and enforced in the
    pre-invocation hook, not just by prompt instruction."

Requirement 11.4: "WHEN an agent attempts to call an MCP tool outside its
configured allowlist THEN the pre-invocation hook SHALL block the call,
independent of what the agent's prompt instructs."

Requirement 11.5: "EACH MCP server used SHALL be a vetted, version-pinned
build, and its output SHALL be treated as untrusted data by consuming
agents." This requirement is an operational/deployment concern (pin each
MCP server's build/version at deploy time, e.g. in the Terraform/container
image that provisions it — out of scope for Task 3.4/Task 14's infra) and
a consuming-agent behavior concern (treat MCP tool *output* as untrusted
data, the same way Task 14.8 treats PR-diff content as untrusted data for
the PR-Reviewer Agent). Neither half is something a Python function can
enforce at call time, so it is documented here rather than code-enforced:
this module only owns the *allowlist* half of Requirement 11 (11.4), which
*is* a pure static lookup this module can and does enforce.

Design choice for Requirement 11.4's "independent of what the agent's
prompt instructs" clause: `enforce_tool_allowlist` takes only `agent` and
`tool` as its enforcement inputs. It never reads or accepts any
prompt/instruction text as part of the allow/deny decision — the function
signature has no parameter through which prompt content could influence
the outcome, so there is no code path an agent's prompt could take to
widen its own allowlist. (`prompt` is accepted as an optional, ignored
keyword-only argument purely so a caller that happens to be threading a
prompt/instruction string through its call sites has somewhere inert to
put it, rather than needing a branch to conditionally omit the argument;
see the tests in `tests/tools/test_allowlist.py` for the confirmation that
its value never affects the result.)
"""

from __future__ import annotations

from enum import StrEnum

from daf.models.types import AgentId


class McpTool(StrEnum):
    """The 7 MCP connector types from design.md's architecture diagram
    ("MCP Connectors — Phase 1") and Dependencies section.
    """

    GITHUB = "GITHUB"
    AWS_API_CLI = "AWS_API_CLI"
    TERRAFORM = "TERRAFORM"
    AZURE = "AZURE"
    S3_KB = "S3_KB"
    FILESYSTEM = "FILESYSTEM"
    AWS_DOCS = "AWS_DOCS"


class AgentRole(StrEnum):
    """The persistent core agents (design.md Component 5) plus the
    on-demand PR-Reviewer and the Supervisor, identifying *which*
    allowlist applies — distinct from `AgentId` (Task 6.1), which
    identifies a specific run's agent instance rather than its role.

    `enforce_tool_allowlist` accepts either an `AgentRole` or a plain
    `AgentId`/`str` whose value matches one of these role names (see
    `_resolve_agent_role`), so callers that only have an `AgentId` in
    hand (e.g. the hook pipeline, which threads `TaskEnvelope`/agent
    identifiers rather than role enums) don't need a separate lookup step.
    """

    SUPERVISOR = "SUPERVISOR"
    DISCOVERY = "DISCOVERY"
    DEVOPS = "DEVOPS"
    SECURITY = "SECURITY"
    MODERNIZATION = "MODERNIZATION"
    PORTFOLIO_ASSESSMENT = "PORTFOLIO_ASSESSMENT"
    PR_REVIEWER = "PR_REVIEWER"


#: Declarative per-agent MCP tool allowlist, seeded directly from
#: design.md Component 5's "Primary tools (MCP)" table.
#:
#: - `SUPERVISOR` is intentionally mapped to an empty allowlist: design.md
#:   Component 1 states the Supervisor "Never call[s] MCP tools or cloud
#:   APIs directly — only spokes do" (Requirement 1.1), so no MCP tool call
#:   made *as* the Supervisor should ever pass this check.
#: - `PR_REVIEWER` is allowlisted for `GITHUB` only. design.md's table
#:   marks this "GitHub MCP (read-only)" — this module does not model a
#:   separate read-only/read-write distinction *within* a tool, because
#:   Task 4.1/4.3's credential scoping (a read-only GitHub token/IAM
#:   policy for the PR-Reviewer's role) is what actually constrains the
#:   PR-Reviewer to read-only GitHub operations at the credential layer;
#:   modeling it again here would be a second, weaker enforcement point
#:   for the same rule. Task 14.8's unit tests separately assert the
#:   PR-Reviewer's *generated actions* never call a merge/approve
#:   operation.
#: - Values are `frozenset`s so a caller can't accidentally mutate a
#:   shared allowlist entry in place.
AGENT_MCP_TOOL_ALLOWLIST: dict[AgentRole, frozenset[McpTool]] = {
    AgentRole.SUPERVISOR: frozenset(),
    AgentRole.DISCOVERY: frozenset({McpTool.AZURE, McpTool.FILESYSTEM}),
    AgentRole.DEVOPS: frozenset({McpTool.GITHUB, McpTool.TERRAFORM, McpTool.AWS_API_CLI}),
    AgentRole.SECURITY: frozenset({McpTool.AWS_API_CLI, McpTool.S3_KB}),
    AgentRole.MODERNIZATION: frozenset({McpTool.AWS_DOCS, McpTool.S3_KB, McpTool.FILESYSTEM}),
    AgentRole.PORTFOLIO_ASSESSMENT: frozenset({McpTool.S3_KB}),
    AgentRole.PR_REVIEWER: frozenset({McpTool.GITHUB}),
}


class ToolNotAllowlistedError(Exception):
    """Raised by `enforce_tool_allowlist` when `tool` is not in `agent`'s
    configured allowlist.

    Carries the resolved `agent_role` and the rejected `tool` as
    structured attributes (rather than only a formatted message) so a
    caller — e.g. the pre-invocation hook (Task 10.1) — can log/audit the
    denial without re-parsing the exception message.
    """

    def __init__(self, agent_role: AgentRole, tool: McpTool) -> None:
        self.agent_role = agent_role
        self.tool = tool
        super().__init__(
            f"Agent role {agent_role.value!r} is not allowlisted to call MCP tool {tool.value!r}"
        )


class UnknownAgentRoleError(Exception):
    """Raised by `enforce_tool_allowlist` when `agent` cannot be resolved
    to a known `AgentRole` (i.e. no allowlist is configured for it at
    all). Kept distinct from `ToolNotAllowlistedError` because this is a
    configuration gap, not a normal allow/deny outcome — a caller should
    generally treat it as a defect rather than a routine block.
    """

    def __init__(self, agent: AgentRole | AgentId | str) -> None:
        self.agent = agent
        super().__init__(f"No MCP tool allowlist is configured for agent {agent!r}")


def _resolve_agent_role(agent: AgentRole | AgentId | str) -> AgentRole:
    """Resolve `agent` to an `AgentRole`, accepting either an `AgentRole`
    directly or a plain `str`/`AgentId` whose value matches a role name
    (case-insensitive), so callers holding only a run-scoped `AgentId`
    don't need a separate role lookup.
    """
    if isinstance(agent, AgentRole):
        return agent
    try:
        return AgentRole(str(agent).upper())
    except ValueError as exc:
        raise UnknownAgentRoleError(agent) from exc


def enforce_tool_allowlist(
    agent: AgentRole | AgentId | str,
    tool: McpTool,
    *,
    prompt: str | None = None,  # noqa: ARG001 - intentionally ignored, see module docstring
) -> None:
    """Raise if `agent` is not allowlisted to call `tool`; otherwise return
    `None` silently.

    This is the `enforceToolAllowlist(agent)` step of design.md Algorithm
    4's pre-invocation stage (Task 10.1), generalized to take the specific
    `tool` being called (design.md's pseudocode elides the tool argument,
    but Requirement 11.4 is specifically about *a call to a tool outside
    the allowlist*, which requires knowing which tool is being called).

    The allow/deny decision is a pure lookup against the static
    `AGENT_MCP_TOOL_ALLOWLIST` config above — it never inspects `prompt`
    or any other agent-generated content, satisfying Requirement 11.4's
    "independent of what the agent's prompt instructs" clause structurally
    (there is no code path from `prompt`'s value to this function's
    outcome).

    Raises:
        UnknownAgentRoleError: `agent` does not resolve to any configured
            `AgentRole` (a configuration gap, not a normal block).
        ToolNotAllowlistedError: `tool` is not in the resolved agent
            role's configured allowlist.
    """
    agent_role = _resolve_agent_role(agent)
    allowed_tools = AGENT_MCP_TOOL_ALLOWLIST.get(agent_role)
    if allowed_tools is None:
        raise UnknownAgentRoleError(agent_role)
    if tool not in allowed_tools:
        raise ToolNotAllowlistedError(agent_role, tool)
