"""MCP tool allowlisting for DAF Phase 1.

Requirement 11.4: "WHEN an agent attempts to call an MCP tool outside its
configured allowlist THEN the pre-invocation hook SHALL block the call,
independent of what the agent's prompt instructs."

Requirement 11.5: "EACH MCP server used SHALL be a vetted, version-pinned
build, and its output SHALL be treated as untrusted data by consuming
agents."

See `daf.tools.allowlist` for the `McpTool` enum, the per-agent allowlist
configuration, and the `enforce_tool_allowlist` function the pre-invocation
hook (Task 10.1, design.md Algorithm 4 `enforceToolAllowlist`) calls.
"""

from daf.tools.allowlist import (
    AGENT_MCP_TOOL_ALLOWLIST,
    AgentRole,
    McpTool,
    ToolNotAllowlistedError,
    UnknownAgentRoleError,
    enforce_tool_allowlist,
)

__all__ = [
    "AGENT_MCP_TOOL_ALLOWLIST",
    "AgentRole",
    "McpTool",
    "ToolNotAllowlistedError",
    "UnknownAgentRoleError",
    "enforce_tool_allowlist",
]
