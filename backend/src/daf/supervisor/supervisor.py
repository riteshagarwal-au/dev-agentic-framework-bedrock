"""Supervisor orchestration (design.md Component 1, Task 12).

Never calls an MCP tool or cloud API directly (Requirement 1.1) — it only
persists `RunState`/`RunCounters` (via the injected repositories) and
delegates all actual agent work to `HookPipeline.invoke_spoke` (Task 10),
which is the sole call site that ever invokes a `SpokeAgent`. Agent-to-
agent handoff is impossible by construction: agents are only ever reached
through `_agent_registry` inside `route_task`, never given a reference to
each other (star topology, Requirement 1.3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from pydantic import ConfigDict, Field

from daf.budget.hook import CostBudgetHook
from daf.models.budget import RunCounters
from daf.models.common import DafBaseModel
from daf.models.enums import RunStatus, SpokeResultStatus
from daf.models.envelope import SpokeResult, TaskEnvelope
from daf.models.run import RunConfig, RunState
from daf.models.types import RunId, TraceId
from daf.pipeline.pipeline import HookPipeline, SpokeAgentProtocol
from daf.supervisor.exceptions import RunNotFoundError, TerminalRunStateError
from daf.supervisor.task_graph import build_task_graph

_TERMINAL_STATUSES = frozenset({RunStatus.HALTED, RunStatus.COMPLETED, RunStatus.FAILED})


class RunHandle(DafBaseModel):
    """Returned by `Supervisor.start_run`."""

    run_id: RunId = Field(alias="runId")
    status: RunStatus

    model_config = ConfigDict(extra="forbid", validate_assignment=True, populate_by_name=True)


class AuditLog(Protocol):
    def write(self, event: str, payload: dict) -> None: ...


class RunStateRepositoryProtocol(Protocol):
    def save(self, run_state: RunState) -> bool: ...
    def get(self, run_id: str) -> RunState | None: ...
    def update_status(self, run_id: str, status: str) -> None: ...


class RunCountersRepositoryProtocol(Protocol):
    def initialize(self, run_id: str) -> None: ...


class Supervisor:
    """`Supervisor` (design.md Component 1)."""

    def __init__(
        self,
        run_state_repo: RunStateRepositoryProtocol,
        run_counters_repo: RunCountersRepositoryProtocol,
        hook_pipeline: HookPipeline,
        budget_hook: CostBudgetHook,
        agent_registry: dict[str, SpokeAgentProtocol],
        audit_log: AuditLog,
    ) -> None:
        """`agent_registry` is keyed by `TaskType` value (not `agentId`) —
        a single agent role can handle more than one `TaskType`, each of
        which needs its own router-policy entry/model tier.
        """
        self._run_state_repo = run_state_repo
        self._run_counters_repo = run_counters_repo
        self._hook_pipeline = hook_pipeline
        self._budget_hook = budget_hook
        self._agent_registry = agent_registry
        self._audit = audit_log

    def start_run(self, run_config: RunConfig) -> RunHandle:
        """Decompose `run_config` into the fixed Phase 1 task graph and
        persist the initial `RunState` — no MCP tool/cloud API call.
        """
        task_graph = build_task_graph(run_config.run_id)
        trace_id = TraceId(str(uuid4()))
        now = datetime.now(UTC)

        self._run_counters_repo.initialize(run_config.run_id)
        run_state = RunState(
            runId=run_config.run_id,
            status=RunStatus.PENDING,
            taskGraph=task_graph,
            currentStepIndex=0,
            traceId=trace_id,
            counters=RunCounters(runId=run_config.run_id),
            createdAt=now,
            updatedAt=now,
        )
        self._run_state_repo.save(run_state)
        self._run_state_repo.update_status(run_config.run_id, RunStatus.RUNNING.value)
        self._audit.write("run_started", {"runId": run_config.run_id, "traceId": trace_id})
        return RunHandle(runId=run_config.run_id, status=RunStatus.RUNNING)

    def route_task(self, run_id: RunId) -> SpokeResult:
        """Route the run's next incomplete task graph node through the
        Router + hook pipeline (Task 10) via the single Supervisor-owned
        call site — the star-topology brokering point.
        """
        run_state = self._run_state_repo.get(run_id)
        if run_state is None:
            raise RunNotFoundError(run_id)
        if run_state.status in _TERMINAL_STATUSES:
            raise TerminalRunStateError(run_id, run_state.status.value)

        node = run_state.task_graph[run_state.current_step_index]
        # Keyed by taskType, not agentId: a single agent role (e.g.
        # Discovery) handles multiple TaskType values, each needing its
        # own router policy entry/tier (agent.task_type feeds resolve_model).
        agent = self._agent_registry[node.task_type]
        envelope = TaskEnvelope(task=node.task_type, inputs={}, traceId=run_state.trace_id)

        result = self._hook_pipeline.invoke_spoke(agent, envelope, run_id)

        if result.status == SpokeResultStatus.PARTIAL:
            # Awaiting a HITL gate decision (raised inside invoke_spoke) —
            # do not advance the task graph; RunState.status was already
            # moved to AWAITING_HITL by the HITL broker itself.
            return result

        node.completed = True
        run_state.current_step_index += 1
        run_state.updated_at = datetime.now(UTC)
        self._run_state_repo.save(run_state)

        if run_state.current_step_index >= len(run_state.task_graph):
            self._run_state_repo.update_status(run_id, RunStatus.COMPLETED.value)

        return result

    def get_run_status(self, run_id: RunId) -> RunStatus:
        run_state = self._run_state_repo.get(run_id)
        if run_state is None:
            raise RunNotFoundError(run_id)
        return run_state.status

    def get_run_state(self, run_id: RunId) -> RunState:
        """Full RunState (task graph + progress), for portal status displays that need more
        than the bare status enum `get_run_status` returns."""
        run_state = self._run_state_repo.get(run_id)
        if run_state is None:
            raise RunNotFoundError(run_id)
        return run_state

    def kill_run(self, run_id: RunId, reason: str) -> None:
        """Stop further routing: activate the kill switch (so any
        in-flight/subsequent `preCheck` halts) and move the run to
        `HALTED`.
        """
        if self._run_state_repo.get(run_id) is None:
            raise RunNotFoundError(run_id)
        self._budget_hook.set_kill_switch(run_id, True)
        self._run_state_repo.update_status(run_id, RunStatus.HALTED.value)
        self._audit.write("run_killed", {"runId": run_id, "reason": reason})
