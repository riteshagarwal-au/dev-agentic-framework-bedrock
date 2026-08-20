"""Integration test: startRun -> routeTask -> HITL gate -> decide(APPROVED) -> resume (Task 12.5)."""

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
from daf.models.enums import GateTicketStatus, HitlGateType, RunStatus, SpokeResultStatus, TargetPlatform, TaskType
from daf.models.run import RunConfig
from daf.persistence.gate_ticket_repository import GateTicketRepository
from daf.persistence.run_counters_repository import RunCountersRepository
from daf.persistence.run_state_repository import RunStateRepository
from daf.pipeline.pipeline import HookPipeline, InMemoryAttemptStateStore
from daf.supervisor.supervisor import Supervisor
from daf.tools.allowlist import AgentRole
from tests.budget.fakes import FakeRunConfigProvider
from tests.hitl.fakes import FakePortalNotifier, FakeStepFunctionsClient
from tests.persistence.fakes import FakeDynamoDBTable
from tests.supervisor.fakes import FakeAuditLog, FakeMemoryManager, FakeOpusGate, FakeTokenEstimator, ScriptedAgent


class GateOnFirstCallResolver:
    """Blocks the very first routed task behind a HITL gate, then clears once decided."""

    def __init__(self) -> None:
        self.raised_once = False

    def find_blocking_gate(self, task_type, run_id):
        if not self.raised_once:
            self.raised_once = True
            return HitlGateType.PLAN_FINALIZE
        return None

    def build_approval_context(self, envelope):
        from daf.models.common import ApprovalContext

        return ApprovalContext(summary="approve plan")


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


def test_start_run_then_hitl_gate_then_approve_resumes_flow() -> None:
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
    gate_tickets = GateTicketRepository(FakeDynamoDBTable(key_name="ticketId"))
    hitl = HitlApprovalBroker(
        gate_tickets, run_state_repo, FakeStepFunctionsClient(), FakePortalNotifier(), FakeAuditLog()
    )
    gate_resolver = GateOnFirstCallResolver()
    pipeline = HookPipeline(
        cost_budget_hook=budget,
        hitl_broker=hitl,
        token_estimator=FakeTokenEstimator(),
        gate_resolver=gate_resolver,
        attempt_state_store=InMemoryAttemptStateStore(),
        audit_log=FakeAuditLog(),
        memory_manager=FakeMemoryManager(),
        opus_gate_for_router=FakeOpusGate(),
    )
    discovery_agent = ScriptedAgent(AgentRole.DISCOVERY.value, TaskType.DISCOVERY_COLLECT)
    agent_registry = {
        TaskType.DISCOVERY_COLLECT: discovery_agent,
        TaskType.DISCOVERY_REASON: ScriptedAgent(AgentRole.DISCOVERY.value, TaskType.DISCOVERY_REASON),
        TaskType.MODERNIZATION_PLAN: ScriptedAgent(AgentRole.MODERNIZATION.value, TaskType.MODERNIZATION_PLAN),
        TaskType.PORTFOLIO_ASSESSMENT: ScriptedAgent(
            AgentRole.PORTFOLIO_ASSESSMENT.value, TaskType.PORTFOLIO_ASSESSMENT
        ),
        TaskType.SECURITY_REVIEW: ScriptedAgent(AgentRole.SECURITY.value, TaskType.SECURITY_REVIEW),
        TaskType.DEVOPS_EXEC: ScriptedAgent(AgentRole.DEVOPS.value, TaskType.DEVOPS_EXEC),
    }
    supervisor = Supervisor(
        run_state_repo=run_state_repo,
        run_counters_repo=run_counters_repo,
        hook_pipeline=pipeline,
        budget_hook=budget,
        agent_registry=agent_registry,
        audit_log=FakeAuditLog(),
    )

    supervisor.start_run(_run_config())
    assert supervisor.get_run_status("run-1") == RunStatus.RUNNING

    # First routeTask hits the blocking gate; the agent must never be invoked.
    blocked_result = supervisor.route_task("run-1")
    assert blocked_result.status == SpokeResultStatus.PARTIAL
    assert discovery_agent.call_count == 0
    assert supervisor.get_run_status("run-1") == RunStatus.AWAITING_HITL
    # Task graph must not have advanced while blocked.
    assert run_state_repo.get("run-1").current_step_index == 0

    pending = hitl.get_pending_gates("run-1")
    assert len(pending) == 1
    ticket_id = pending[0].ticket_id
    assert pending[0].status == GateTicketStatus.PENDING

    hitl.decide(ticket_id, GateTicketStatus.APPROVED, approver="user-1")
    assert supervisor.get_run_status("run-1") == RunStatus.RUNNING

    # Re-routing the same (still-current) task graph node now succeeds and advances.
    resumed_result = supervisor.route_task("run-1")
    assert resumed_result.status == SpokeResultStatus.SUCCESS
    assert discovery_agent.call_count == 1
    assert run_state_repo.get("run-1").current_step_index == 1
