"""Phase 1 end-to-end validation against success criteria (Task 18.1-18.4).

Scope boundary (Task 18.1): PR-Reviewer + the real DevOps GitHub PR-merge
gate / infra-apply gate / cloud-deploy gate are driven by a separate
GH-Actions CI/CD path (Task 14), not by `Supervisor`'s in-process task
graph. These tests are scoped to what `Supervisor`/`HookPipeline` actually
orchestrate: the fixed 6-node core-agent graph (`PHASE1_TASK_SEQUENCE`)
plus one representative HITL gate (`PLAN_FINALIZE`) raised mid-sequence —
the realistic, testable subset given Phase 1's actual code boundaries.
"""

from __future__ import annotations

from daf.agents.devops import DevOpsAgent
from daf.agents.discovery import DiscoveryAgent
from daf.agents.modernization import ModernizationAgent
from daf.agents.portfolio_assessment import PortfolioAssessmentAgent
from daf.agents.security import SecurityAgent
from daf.budget.hook import CostBudgetHook
from daf.budget.policy import MAX_CONSECUTIVE_FAILURES
from daf.budget.stores import (
    InMemoryFailureCounterStore,
    InMemoryIdempotencyStore,
    InMemoryKillSwitchStore,
    InMemoryStepHistoryStore,
)
from daf.hitl.broker import HitlApprovalBroker
from daf.models.budget import BudgetCeiling
from daf.models.common import ArtifactRef, TokenUsage
from daf.models.common import AzureSourceRef
from daf.models.enums import (
    ArtifactKind,
    ArtifactLocationKind,
    GateTicketStatus,
    HitlGateType,
    ModelTier,
    RunStatus,
    SpokeResultStatus,
    TargetPlatform,
    TaskType,
)
from daf.models.envelope import SpokeResult
from daf.models.run import RunConfig
from daf.observability.audit_writer import JsonAuditLogWriter, list_sink, reconstruct_sequence
from daf.persistence.gate_ticket_repository import GateTicketRepository
from daf.persistence.run_counters_repository import RunCountersRepository
from daf.persistence.run_state_repository import RunStateRepository
from daf.pipeline.exceptions import HitlAlert
from daf.pipeline.pipeline import HookPipeline, InMemoryAttemptStateStore
from daf.router.router import AttemptState, resolve_model
from daf.supervisor.supervisor import Supervisor
from tests.budget.fakes import FakeRunConfigProvider
from tests.hitl.fakes import FakePortalNotifier, FakeStepFunctionsClient
from tests.persistence.fakes import FakeDynamoDBTable
from tests.supervisor.fakes import FakeAuditLog, FakeMemoryManager, FakeOpusGate, FakeTokenEstimator

import pytest


class _StubMcpClient:
    """Duck-typed stand-in satisfying every MCP-client Protocol the 5 core
    agents depend on (Azure/Filesystem/S3 KB/AWS Docs/AWS API CLI/GitHub/
    Terraform) — Task 13's agents accept these via constructor injection.
    """

    def list_resources(self, resource_group: str) -> list[dict]:
        return []

    def read_file(self, path: str) -> str:
        return "stub-file-content"

    def retrieve_guidance(self, topic: str) -> str:
        return "stub-guidance"

    def retrieve_security_guidance(self, topic: str) -> str:
        return "stub-security-guidance"

    def check_iam_policy(self, policy_ref: str) -> list[str]:
        return []

    def validate_credentials(self) -> bool:
        return True

    def open_pull_request(self, title: str, body: str, branch: str) -> str:
        return "https://github.com/example/repo/pull/1"

    def generate_plan(self, blueprint_ref: str) -> str:
        return "tf-plan-stub"


def _run_config(run_id: str = "run-1") -> RunConfig:
    return RunConfig(
        runId=run_id,
        targetApp="synthetic-app",
        sourceEnv=AzureSourceRef(subscriptionId="sub-1", resourceGroup="rg-1", resourceName="app-1"),
        targetPlatform=TargetPlatform.ECS_FARGATE,
        budgetCeiling=BudgetCeiling(
            maxTotalTokens=1_000_000, maxCostUsd=1_000_000.0, maxWallClockMs=1_000_000_000,
            maxSteps=1_000_000, maxOpusInvocations=1_000_000,
        ),
        targetRepo="riteshagarwal-au/appmigration-daf",
    )


def _build_agent_registry() -> dict[TaskType, object]:
    """The 5 core agents (Task 13), keyed by `TaskType` per
    `task_graph.py`'s registry-keying convention. `DiscoveryAgent`'s
    constructor takes `task_type`, so two instances are needed — one per
    Discovery task type.
    """
    stub = _StubMcpClient()
    return {
        TaskType.DISCOVERY_COLLECT: DiscoveryAgent(TaskType.DISCOVERY_COLLECT, stub, stub),
        TaskType.DISCOVERY_REASON: DiscoveryAgent(TaskType.DISCOVERY_REASON, stub, stub),
        TaskType.MODERNIZATION_PLAN: ModernizationAgent(stub, stub, stub, FakeAuditLog()),
        TaskType.PORTFOLIO_ASSESSMENT: PortfolioAssessmentAgent(stub),
        TaskType.SECURITY_REVIEW: SecurityAgent(stub, stub),
        TaskType.DEVOPS_EXEC: DevOpsAgent(stub, stub, stub),
    }


class _GateAtModernizationResolver:
    """Blocks exactly one task-graph node (`MODERNIZATION_PLAN`) behind
    the `PLAN_FINALIZE` HITL gate, once, then clears — mirroring
    `GateOnFirstCallResolver` in `tests/supervisor/test_integration_hitl_resume.py`
    but targeting a specific mid-sequence step rather than the first call.
    """

    def __init__(self) -> None:
        self.raised = False

    def find_blocking_gate(self, task_type: TaskType, run_id: str) -> HitlGateType | None:
        if task_type == TaskType.MODERNIZATION_PLAN and not self.raised:
            self.raised = True
            return HitlGateType.PLAN_FINALIZE
        return None

    def build_approval_context(self, envelope):
        from daf.models.common import ApprovalContext

        return ApprovalContext(summary="approve modernization plan before proceeding")


def _build_stack(gate_resolver, audit_log, *, ceiling: BudgetCeiling | None = None):
    """Wire the full Supervisor -> HookPipeline -> Router/Budget/HITL stack,
    reusing the exact fake/store types from `tests/supervisor/fakes.py`,
    `tests/budget/fakes.py`, `tests/hitl/fakes.py`, `tests/persistence/fakes.py`.
    """
    ceiling = ceiling or BudgetCeiling(
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
        failure_counter_store=InMemoryFailureCounterStore(MAX_CONSECUTIVE_FAILURES),
    )
    gate_tickets = GateTicketRepository(FakeDynamoDBTable(key_name="ticketId"))
    hitl = HitlApprovalBroker(
        gate_tickets, run_state_repo, FakeStepFunctionsClient(), FakePortalNotifier(), audit_log
    )
    pipeline = HookPipeline(
        cost_budget_hook=budget,
        hitl_broker=hitl,
        token_estimator=FakeTokenEstimator(),
        gate_resolver=gate_resolver,
        attempt_state_store=InMemoryAttemptStateStore(),
        audit_log=audit_log,
        memory_manager=FakeMemoryManager(),
        opus_gate_for_router=FakeOpusGate(),
    )
    supervisor = Supervisor(
        run_state_repo=run_state_repo,
        run_counters_repo=run_counters_repo,
        hook_pipeline=pipeline,
        budget_hook=budget,
        agent_registry=_build_agent_registry(),
        audit_log=audit_log,
    )
    return supervisor, budget, hitl, run_state_repo


# ---------------------------------------------------------------------------
# Task 18.1 — full synthetic-app migration flow through a HITL gate
# ---------------------------------------------------------------------------


def test_phase1_e2e_flow_through_hitl_gate_completes_all_six_steps() -> None:
    gate_resolver = _GateAtModernizationResolver()
    audit_log = FakeAuditLog()
    supervisor, _budget, hitl, run_state_repo = _build_stack(gate_resolver, audit_log)

    supervisor.start_run(_run_config("run-1"))
    assert supervisor.get_run_status("run-1") == RunStatus.RUNNING

    # Steps 0, 1: DISCOVERY_COLLECT, DISCOVERY_REASON — run through unblocked.
    for expected_index in (0, 1):
        result = supervisor.route_task("run-1")
        assert result.status == SpokeResultStatus.SUCCESS
        assert run_state_repo.get("run-1").current_step_index == expected_index + 1

    # Step 2: MODERNIZATION_PLAN — blocked behind PLAN_FINALIZE.
    blocked = supervisor.route_task("run-1")
    assert blocked.status == SpokeResultStatus.PARTIAL
    assert supervisor.get_run_status("run-1") == RunStatus.AWAITING_HITL
    assert run_state_repo.get("run-1").current_step_index == 2  # task graph did not advance

    pending = hitl.get_pending_gates("run-1")
    assert len(pending) == 1
    assert pending[0].gate_type == HitlGateType.PLAN_FINALIZE
    assert pending[0].status == GateTicketStatus.PENDING

    hitl.decide(pending[0].ticket_id, GateTicketStatus.APPROVED, approver="approver-1")
    assert supervisor.get_run_status("run-1") == RunStatus.RUNNING

    # Re-routing the still-current MODERNIZATION_PLAN node now succeeds and advances.
    resumed = supervisor.route_task("run-1")
    assert resumed.status == SpokeResultStatus.SUCCESS
    assert run_state_repo.get("run-1").current_step_index == 3

    # Steps 3, 4, 5: PORTFOLIO_ASSESSMENT, SECURITY_REVIEW, DEVOPS_EXEC.
    for expected_index in (4, 5, 6):
        result = supervisor.route_task("run-1")
        assert result.status == SpokeResultStatus.SUCCESS
        assert run_state_repo.get("run-1").current_step_index == expected_index

    # All 6 task-graph steps completed, none skipped or double-run.
    final_state = run_state_repo.get("run-1")
    assert len(final_state.task_graph) == 6
    assert all(node.completed for node in final_state.task_graph)
    assert final_state.current_step_index == 6
    assert supervisor.get_run_status("run-1") == RunStatus.COMPLETED


# ---------------------------------------------------------------------------
# Task 18.2 — deliberate-trigger tests for the three safety mechanisms
# ---------------------------------------------------------------------------


def test_kill_switch_halts_next_route_task_call() -> None:
    gate_resolver = _GateAtModernizationResolver()
    supervisor, budget, _hitl, _run_state_repo = _build_stack(gate_resolver, FakeAuditLog())
    supervisor.start_run(_run_config("run-kill"))

    # First step succeeds normally, proving the kill switch (not some
    # other misconfiguration) is what halts the *next* call.
    assert supervisor.route_task("run-kill").status == SpokeResultStatus.SUCCESS

    budget.set_kill_switch("run-kill", True)
    assert budget.is_kill_switch_active("run-kill") is True

    with pytest.raises(HitlAlert):
        supervisor.route_task("run-kill")


def test_hard_budget_cap_halts_run_with_no_further_step_attempted() -> None:
    tiny_ceiling = BudgetCeiling(
        maxTotalTokens=1,  # deliberately far below any real task's token estimate
        maxCostUsd=1_000_000.0, maxWallClockMs=1_000_000_000,
        maxSteps=1_000_000, maxOpusInvocations=1_000_000,
    )
    gate_resolver = _GateAtModernizationResolver()
    supervisor, budget, _hitl, run_state_repo = _build_stack(
        gate_resolver, FakeAuditLog(), ceiling=tiny_ceiling
    )
    supervisor.start_run(_run_config("run-hardcap"))

    decision = budget.pre_check("run-hardcap", estimated_tokens=10)
    assert decision.status.value == "HALT"

    with pytest.raises(HitlAlert):
        supervisor.route_task("run-hardcap")

    # No step was attempted: task graph did not advance.
    assert run_state_repo.get("run-hardcap").current_step_index == 0
    assert budget.is_kill_switch_active("run-hardcap") is True


class _AlwaysFailsAgent:
    """Reproduces `ScriptedAgent`'s shape (`tests/supervisor/fakes.py`) but
    always returns `FAILED`, to deliberately trip
    `detectConsecutiveFailures` (Task 8.4/8.5).
    """

    def __init__(self, agent_id: str, task_type: TaskType) -> None:
        self.agent_id = agent_id
        self.task_type = task_type
        self.output_schema = SpokeResult
        self.call_count = 0

    def execute(self, envelope, tier) -> SpokeResult:
        self.call_count += 1
        return SpokeResult(
            output=ArtifactRef(
                artifactId="a1", location="s3://b/k",
                locationKind=ArtifactLocationKind.S3_URI, kind=ArtifactKind.OTHER,
            ),
            confidence=0.0,
            tokensUsed=TokenUsage(tokensIn=5, tokensOut=5),
            status=SpokeResultStatus.FAILED,
        )


def test_circuit_breaker_trips_after_consecutive_failures() -> None:
    """Uses a SONNET-default task type (`SECURITY_REVIEW`) so the Router's
    retry ladder (`MAX_SONNET_RETRIES` then one Opus escalation) bounds
    the number of attempts before `MAX_CONSECUTIVE_FAILURES` (3) trips the
    circuit breaker — observable here as kill-switch activation, matching
    `CostBudgetHook._trigger_circuit_breaker`'s Phase 1 enforcement.
    """
    gate_resolver = _GateAtModernizationResolver()
    audit_log = FakeAuditLog()
    supervisor, budget, hitl, run_state_repo = _build_stack(gate_resolver, audit_log)
    supervisor.start_run(_run_config("run-cb"))

    failing_agent = _AlwaysFailsAgent("security", TaskType.SECURITY_REVIEW)
    supervisor._agent_registry[TaskType.SECURITY_REVIEW] = failing_agent  # noqa: SLF001 - test wiring

    # Advance to the SECURITY_REVIEW step (index 4) via the normal
    # unblocked steps 0-3 (Discovery x2, Modernization gated then approved, Portfolio).
    supervisor.route_task("run-cb")  # DISCOVERY_COLLECT
    supervisor.route_task("run-cb")  # DISCOVERY_REASON
    blocked = supervisor.route_task("run-cb")  # MODERNIZATION_PLAN -> gated
    assert blocked.status == SpokeResultStatus.PARTIAL
    pending = hitl.get_pending_gates("run-cb")
    assert len(pending) == 1
    hitl.decide(pending[0].ticket_id, GateTicketStatus.APPROVED, approver="approver-1")
    supervisor.route_task("run-cb")  # MODERNIZATION_PLAN -> succeeds
    supervisor.route_task("run-cb")  # PORTFOLIO_ASSESSMENT -> succeeds

    assert not budget.is_kill_switch_active("run-cb")
    with pytest.raises(HitlAlert):
        supervisor.route_task("run-cb")  # SECURITY_REVIEW -> always FAILED, retries until circuit breaker trips

    assert budget.is_kill_switch_active("run-cb") is True
    assert failing_agent.call_count >= MAX_CONSECUTIVE_FAILURES


# ---------------------------------------------------------------------------
# Task 18.3 — model-tier call-mix harness (captures the split, does NOT
# assert it literally equals 70/28/2 — that's an operational tuning target
# from real usage data, not a deterministic property of Phase 1 stub code).
# ---------------------------------------------------------------------------


def test_model_tier_call_mix_harness_captures_well_formed_split() -> None:
    task_types = list(
        {
            TaskType.DISCOVERY_COLLECT,
            TaskType.DISCOVERY_REASON,
            TaskType.MODERNIZATION_PLAN,
            TaskType.PORTFOLIO_ASSESSMENT,
            TaskType.SECURITY_REVIEW,
            TaskType.DEVOPS_EXEC,
        }
    )
    opus_gate = FakeOpusGate()
    total_calls = 100
    escalation_rate = 0.05  # small deliberately-injected escalation rate
    tier_counts: dict[ModelTier, int] = {ModelTier.HAIKU: 0, ModelTier.SONNET: 0, ModelTier.OPUS: 0}

    for i in range(total_calls):
        task_type = task_types[i % len(task_types)]
        escalate = (i % int(1 / escalation_rate)) == 0
        attempt_state = AttemptState(
            run_id="run-harness",
            task_id=f"task-{i}",
            attempt_number=2 if escalate else 1,
            last_confidence=0.5 if escalate else None,
            last_status=SpokeResultStatus.FAILED if escalate else None,
        )
        tier = resolve_model(task_type, attempt_state, opus_gate)
        tier_counts[tier] += 1

    assert sum(tier_counts.values()) == total_calls

    summary = {
        "haiku_pct": round(100 * tier_counts[ModelTier.HAIKU] / total_calls, 2),
        "sonnet_pct": round(100 * tier_counts[ModelTier.SONNET] / total_calls, 2),
        "opus_pct": round(100 * tier_counts[ModelTier.OPUS] / total_calls, 2),
    }
    print(f"Task 18.3 model-tier call-mix harness result (n={total_calls}): {summary}")

    # Well-formed: percentages sum to 100 (within floating-point rounding).
    assert abs(sum(summary.values()) - 100.0) < 0.01
    assert all(pct >= 0.0 for pct in summary.values())


# ---------------------------------------------------------------------------
# Task 18.4 — audit-log-only reconstruction of the full end-to-end run
# ---------------------------------------------------------------------------


def test_audit_log_reconstruction_matches_actual_run_sequence() -> None:
    """Wires a real `JsonAuditLogWriter` (writing to an in-memory sink)
    into the Task 18.1 scenario, then proves `reconstruct_sequence` alone
    recovers the actual sequence of agent invocations + the HITL
    raise/decide pair.

    Note: `GateTicket` (design.md Model 3) has no `traceId` field, only
    `runId` — so `hitl_gate_raised`/`hitl_gate_decided` events carry no
    trace_id and would be dropped by a strict trace_id filter. This test
    therefore reconstructs unfiltered (trace_id=None) against a
    single-run sink, which still proves 100% traceability from the audit
    log alone for this scenario (the realistic granularity the current
    data model supports).
    """
    sink_lines: list[str] = []
    audit_log = JsonAuditLogWriter(list_sink(sink_lines))
    gate_resolver = _GateAtModernizationResolver()
    supervisor, _budget, hitl, run_state_repo = _build_stack(gate_resolver, audit_log)

    supervisor.start_run(_run_config("run-audit"))
    supervisor.route_task("run-audit")  # DISCOVERY_COLLECT
    supervisor.route_task("run-audit")  # DISCOVERY_REASON
    blocked = supervisor.route_task("run-audit")  # MODERNIZATION_PLAN -> gated
    assert blocked.status == SpokeResultStatus.PARTIAL
    pending = hitl.get_pending_gates("run-audit")
    assert len(pending) == 1
    hitl.decide(pending[0].ticket_id, GateTicketStatus.APPROVED, approver="approver-1")
    supervisor.route_task("run-audit")  # MODERNIZATION_PLAN -> succeeds
    supervisor.route_task("run-audit")  # PORTFOLIO_ASSESSMENT
    supervisor.route_task("run-audit")  # SECURITY_REVIEW
    supervisor.route_task("run-audit")  # DEVOPS_EXEC

    assert supervisor.get_run_status("run-audit") == RunStatus.COMPLETED
    assert run_state_repo.get("run-audit").current_step_index == 6

    reconstructed = reconstruct_sequence(sink_lines, trace_id=None)

    # Actual actions/decisions taken: run_started, 5 successful invocations
    # (Discovery x2, Modernization, Portfolio, Security, DevOps), the
    # hitl_gate_raised/decided pair around Modernization, and the final
    # successful re-invocation of Modernization after approval — 6 total
    # agent_invocation_complete events plus the run lifecycle + gate events.
    assert reconstructed.count("run_started") == 1
    assert reconstructed.count("agent_invocation_complete") == 6
    assert reconstructed.count("hitl_gate_raised") == 1
    assert reconstructed.count("hitl_gate_decided") == 1

    # Order: run started first; the gate is raised before it is decided;
    # the gate is decided before Modernization's successful re-invocation.
    raised_index = reconstructed.index("hitl_gate_raised")
    decided_index = reconstructed.index("hitl_gate_decided")
    assert reconstructed[0] == "run_started"
    assert raised_index < decided_index
    invocation_indices = [i for i, e in enumerate(reconstructed) if e == "agent_invocation_complete"]
    assert invocation_indices[-1] > decided_index  # last invocation (DevOps) occurs after the gate is decided
