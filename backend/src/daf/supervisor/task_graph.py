"""Fixed Phase 1 task-graph decomposition (Task 12.1).

design.md's main-flow sequence diagram runs Discovery -> Modernization ->
plan-finalize gate -> Security -> DevOps -> PR (Task 14, on-demand, not a
core-agent task-graph node) -> further gates. This module encodes the
5-core-agent subset of that sequence as a fixed, deterministic task graph
— Phase 1 has exactly one task-graph shape per run, no dynamic planning.
"""

from __future__ import annotations

from daf.models.common import TaskNode
from daf.models.enums import TaskType
from daf.tools.allowlist import AgentRole

#: (TaskType, AgentRole) pairs in the fixed Phase 1 execution order.
PHASE1_TASK_SEQUENCE: tuple[tuple[TaskType, AgentRole], ...] = (
    (TaskType.DISCOVERY_COLLECT, AgentRole.DISCOVERY),
    (TaskType.DISCOVERY_REASON, AgentRole.DISCOVERY),
    (TaskType.MODERNIZATION_PLAN, AgentRole.MODERNIZATION),
    (TaskType.PORTFOLIO_ASSESSMENT, AgentRole.PORTFOLIO_ASSESSMENT),
    (TaskType.SECURITY_REVIEW, AgentRole.SECURITY),
    (TaskType.DEVOPS_EXEC, AgentRole.DEVOPS),
)


def build_task_graph(run_id: str) -> list[TaskNode]:
    """Build the fixed Phase 1 task graph for a new run.

    `taskId` is `"<run_id>-<index>"` — stable and unique within a run,
    without needing a separate ID generator/collision check.
    """
    return [
        TaskNode(
            taskId=f"{run_id}-{index}",
            taskType=task_type.value,
            agentId=agent_role.value,
        )
        for index, (task_type, agent_role) in enumerate(PHASE1_TASK_SEQUENCE)
    ]
