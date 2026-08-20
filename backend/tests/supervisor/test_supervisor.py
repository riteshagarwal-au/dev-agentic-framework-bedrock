"""Unit tests for Supervisor orchestration and star-topology brokering (Task 12.4)."""

from daf.budget.hook import CostBudgetHook
from daf.budget.stores import (
    InMemoryFailureCounterStore,
    InMemoryIdempotencyStore,
    InMemoryKillSwitchStore,
    InMemoryStepHistoryStore,
)
from daf.hitl.broker import HitlApprovalBroker
from daf.models.budget import BudgetCeiling
from daf.models.common import AzureSourceRef
from daf.models.enums import RunStatus, TargetPlatform, TaskType
from daf.models.run import RunConfig
from daf.persistence.gate_ticket_repository import GateTicketRepository
from daf.persistence.run_counters_repository import RunCountersRepository
from daf.persistence.run_state_repository import RunStateRepository
from daf.pipeline.pipeline import HookPipeline, InMemoryAttemptStateStore
from daf.supervisor.exceptions import RunNotFoundError, TerminalRunStateError
from daf.supervisor.supervisor import Supervisor
from daf.tools.allowlist import AgentRole
from tests.budget.fakes import FakeRunConfigProvider
from tests.hitl.fakes import FakePortalNotifier, FakeStepFunctionsClient
from tests.persistence.fakes import FakeDynamoDBTable
from tests.supervisor.fakes import (
    FakeAuditLog,
    FakeGateResolver,
    FakeMemoryManager,
    FakeOpusGate,
    FakeTokenEstimator,
    ScriptedAgent,
)


def _run_config() -> RunConfig:
    return RunConfig(
        runId="run-1",
        targetApp="synthetic-app",
        sourceEnv=AzureSourceRef(subscriptionId="sub-1", resourceGroup="rg-1", resourceName="app-1"),
        targetPlatform=TargetPlatform.ECS_FARGATE,
        budgetCeiling=BudgetCeiling(
            maxTotalTokens=1_000_000, maxCostUsd=1_000_000.0, maxWallClockMs=1_000_000_000,
            maxSteps=1_000_000, maxOpusInvocations=1_000_000,
        ),
        targetRepo="riteshagarwal-au/appmigration-daf",
    )


def _make_supervisor(*, gate=None):
    ceiling = BudgetCeiling(
        maxTotalTokens=1_000_000, maxCostUsd=1_000_000.0, maxWallClockMs=1_000_000_000,
        maxSteps=1_000_000, maxOpusInvocations=1_000_000,
    )
    run_state_repo = RunStateRepository(FakeDynamoDBTable(key_name="runId"))
    run_counters_repo = RunCountersRepository(FakeDynamoDBTable(key_name="runId"))
    budget = CostBudgetHook(
        run_counters_repo=run_counters_repo,
        run_config_provider=FakeRunConfigProvider(ceiling),
        kill_switch_store=InMemoryKillSwitchStore(),
        idempotency_store=InMemoryIdempotencyStore(),
        step_history_store=InMemoryStepHistoryStore(),
        failure_counter_store=InMemoryFailureCounterStore(1_000_000),
    )
    hitl = HitlApprovalBroker(
        GateTicketRepository(FakeDynamoDBTable(key_name="ticketId")),
        run_state_repo,
        FakeStepFunctionsClient(),
        FakePortalNotifier(),
        FakeAuditLog(),
    )
    pipeline_audit = FakeAuditLog()
    pipeline = HookPipeline(
        cost_budget_hook=budget,
        hitl_broker=hitl,
        token_estimator=FakeTokenEstimator(),
        gate_resolver=FakeGateResolver(gate),
        attempt_state_store=InMemoryAttemptStateStore(),
        audit_log=pipeline_audit,
        memory_manager=FakeMemoryManager(),
        opus_gate_for_router=FakeOpusGate(),
    )
    discovery_collect_agent = ScriptedAgent(AgentRole.DISCOVERY.value, TaskType.DISCOVERY_COLLECT)
    agent_registry = {
        TaskType.DISCOVERY_COLLECT: discovery_collect_agent,
        TaskType.DISCOVERY_REASON: ScriptedAgent(AgentRole.DISCOVERY.value, TaskType.DISCOVERY_REASON),
        TaskType.MODERNIZATION_PLAN: ScriptedAgent(AgentRole.MODERNIZATION.value, TaskType.MODERNIZATION_PLAN),
        TaskType.PORTFOLIO_ASSESSMENT: ScriptedAgent(
            AgentRole.PORTFOLIO_ASSESSMENT.value, TaskType.PORTFOLIO_ASSESSMENT
        ),
        TaskType.SECURITY_REVIEW: ScriptedAgent(AgentRole.SECURITY.value, TaskType.SECURITY_REVIEW),
        TaskType.DEVOPS_EXEC: ScriptedAgent(AgentRole.DEVOPS.value, TaskType.DEVOPS_EXEC),
    }
    supervisor_audit = FakeAuditLog()
    supervisor = Supervisor(
        run_state_repo=run_state_repo,
        run_counters_repo=run_counters_repo,
        hook_pipeline=pipeline,
        budget_hook=budget,
        agent_registry=agent_registry,
        audit_log=supervisor_audit,
    )
    return supervisor, run_state_repo, agent_registry, supervisor_audit


class TestStartRun:
    def test_never_calls_agent_or_mcp_tool_and_persists_running_state(self) -> None:
        supervisor, run_state_repo, agent_registry, audit = _make_supervisor()

        handle = supervisor.start_run(_run_config())

        assert handle.status == RunStatus.RUNNING
        assert all(agent.call_count == 0 for agent in agent_registry.values())
        persisted = run_state_repo.get("run-1")
        assert persisted is not None
        assert persisted.status == RunStatus.RUNNING
        assert len(persisted.task_graph) == 6
        assert any(event == "run_started" for event, _ in audit.events)


class TestRouteTask:
    def test_routes_through_supervisor_star_topology_and_advances_graph(self) -> None:
        supervisor, run_state_repo, agent_registry, _ = _make_supervisor()
        supervisor.start_run(_run_config())

        result = supervisor.route_task("run-1")

        assert result.status.value == "SUCCESS"
        # Only the first node's agent (discovery collect) was invoked - no
        # direct agent-to-agent handoff, no other agent touched.
        assert agent_registry[TaskType.DISCOVERY_COLLECT].call_count == 1
        assert all(
            a.call_count == 0 for task_type, a in agent_registry.items() if task_type != TaskType.DISCOVERY_COLLECT
        )
        persisted = run_state_repo.get("run-1")
        assert persisted.current_step_index == 1
        assert persisted.task_graph[0].completed is True

    def test_runs_to_completion_across_all_six_nodes(self) -> None:
        supervisor, run_state_repo, _, _ = _make_supervisor()
        supervisor.start_run(_run_config())

        for _ in range(6):
            supervisor.route_task("run-1")

        persisted = run_state_repo.get("run-1")
        assert persisted.status == RunStatus.COMPLETED
        assert all(node.completed for node in persisted.task_graph)

    def test_terminal_run_rejects_further_routing(self) -> None:
        supervisor, _, _, _ = _make_supervisor()
        supervisor.start_run(_run_config())
        supervisor.kill_run("run-1", "test halt")

        try:
            supervisor.route_task("run-1")
            raised = False
        except TerminalRunStateError:
            raised = True
        assert raised


class TestGetRunStatusAndKillRun:
    def test_get_run_status_reflects_task_graph_state(self) -> None:
        supervisor, _, _, _ = _make_supervisor()
        supervisor.start_run(_run_config())

        assert supervisor.get_run_status("run-1") == RunStatus.RUNNING

    def test_unknown_run_raises_not_found(self) -> None:
        supervisor, _, _, _ = _make_supervisor()

        try:
            supervisor.get_run_status("nonexistent")
            raised = False
        except RunNotFoundError:
            raised = True
        assert raised

    def test_kill_run_halts_and_activates_kill_switch(self) -> None:
        supervisor, run_state_repo, _, audit = _make_supervisor()
        supervisor.start_run(_run_config())

        supervisor.kill_run("run-1", "budget exceeded upstream")

        assert supervisor.get_run_status("run-1") == RunStatus.HALTED
        assert any(event == "run_killed" for event, _ in audit.events)
