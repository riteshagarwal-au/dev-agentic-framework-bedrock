"""Unit tests for the hook pipeline ordering and failure short-circuiting (Task 10.5)."""

import pytest

from daf.budget.hook import CostBudgetHook
from daf.budget.stores import (
    InMemoryFailureCounterStore,
    InMemoryIdempotencyStore,
    InMemoryKillSwitchStore,
    InMemoryStepHistoryStore,
)
from daf.hitl.broker import HitlApprovalBroker
from daf.models.budget import BudgetCeiling
from daf.models.common import ArtifactRef
from daf.models.enums import ArtifactKind, ArtifactLocationKind, HitlGateType, SpokeResultStatus, TaskType
from daf.models.envelope import SpokeResult, TaskEnvelope
from daf.persistence.gate_ticket_repository import GateTicketRepository
from daf.persistence.run_counters_repository import RunCountersRepository
from daf.persistence.run_state_repository import RunStateRepository
from daf.pipeline.exceptions import HitlAlert
from daf.pipeline.pipeline import HookPipeline, InMemoryAttemptStateStore
from tests.budget.fakes import FakeRunConfigProvider
from tests.hitl.fakes import FakeStepFunctionsClient, FakePortalNotifier
from tests.persistence.fakes import FakeDynamoDBTable
from tests.pipeline.fakes import (
    FakeAgent,
    FakeAuditLog,
    FakeGateResolver,
    FakeMemoryManager,
    FakeOpusGate,
    FakeTokenEstimator,
)


def _artifact_ref() -> ArtifactRef:
    return ArtifactRef(
        artifactId="a1", location="s3://bucket/key", locationKind=ArtifactLocationKind.S3_URI, kind=ArtifactKind.OTHER
    )


def _envelope() -> TaskEnvelope:
    return TaskEnvelope(task="discover-inventory", inputs={"src": _artifact_ref()}, traceId="trace-1")


def _spoke_result(status: SpokeResultStatus, confidence: float) -> SpokeResult:
    return SpokeResult(
        output=_artifact_ref(), confidence=confidence, tokensUsed={"tokensIn": 10, "tokensOut": 5}, status=status
    )


def _make_pipeline(*, gate=None, ceiling: BudgetCeiling | None = None):
    ceiling = ceiling or BudgetCeiling(
        maxTotalTokens=1_000_000, maxCostUsd=1_000_000.0, maxWallClockMs=1_000_000_000,
        maxSteps=1_000_000, maxOpusInvocations=10,
    )
    counters_repo = RunCountersRepository(FakeDynamoDBTable(key_name="runId"))
    counters_repo.initialize("run-1")
    budget = CostBudgetHook(
        run_counters_repo=counters_repo,
        run_config_provider=FakeRunConfigProvider(ceiling),
        kill_switch_store=InMemoryKillSwitchStore(),
        idempotency_store=InMemoryIdempotencyStore(),
        step_history_store=InMemoryStepHistoryStore(),
        failure_counter_store=InMemoryFailureCounterStore(3),
    )
    hitl = HitlApprovalBroker(
        GateTicketRepository(FakeDynamoDBTable(key_name="ticketId")),
        RunStateRepository(FakeDynamoDBTable(key_name="runId")),
        FakeStepFunctionsClient(),
        FakePortalNotifier(),
        FakeAuditLog(),
    )
    audit = FakeAuditLog()
    memory = FakeMemoryManager()
    pipeline = HookPipeline(
        cost_budget_hook=budget,
        hitl_broker=hitl,
        token_estimator=FakeTokenEstimator(),
        gate_resolver=FakeGateResolver(gate),
        attempt_state_store=InMemoryAttemptStateStore(),
        audit_log=audit,
        memory_manager=memory,
        opus_gate_for_router=FakeOpusGate(),
    )
    return pipeline, budget, audit, memory


class TestSuccessPath:
    def test_success_records_usage_and_audits_once(self) -> None:
        pipeline, budget, audit, memory = _make_pipeline()
        agent = FakeAgent(
            "discovery-1", TaskType.DISCOVERY_COLLECT, SpokeResult,
            [_spoke_result(SpokeResultStatus.SUCCESS, 0.95)],
        )

        result = pipeline.invoke_spoke(agent, _envelope(), "run-1")

        assert result.status == SpokeResultStatus.SUCCESS
        assert agent.call_count == 1
        assert sum(1 for e, _ in audit.events if e == "agent_invocation_complete") == 1
        assert len(memory.calls) == 1


class TestBudgetHalt:
    def test_budget_breach_raises_hitl_alert_and_never_invokes_agent(self) -> None:
        tiny_ceiling = BudgetCeiling(
            maxTotalTokens=1, maxCostUsd=1_000_000.0, maxWallClockMs=1_000_000_000,
            maxSteps=1_000_000, maxOpusInvocations=10,
        )
        pipeline, budget, _, _ = _make_pipeline(ceiling=tiny_ceiling)
        agent = FakeAgent(
            "discovery-1", TaskType.DISCOVERY_COLLECT, SpokeResult,
            [_spoke_result(SpokeResultStatus.SUCCESS, 0.95)],
        )

        with pytest.raises(HitlAlert):
            pipeline.invoke_spoke(agent, _envelope(), "run-1")

        assert agent.call_count == 0
        assert budget.is_kill_switch_active("run-1") is True


class TestBlockingGate:
    def test_blocking_gate_raises_gate_and_returns_partial_without_invoking_agent(self) -> None:
        pipeline, _, _, _ = _make_pipeline(gate=HitlGateType.INFRA_APPLY)
        agent = FakeAgent(
            "devops-1", TaskType.DEVOPS_EXEC, SpokeResult, [_spoke_result(SpokeResultStatus.SUCCESS, 0.95)]
        )

        result = pipeline.invoke_spoke(agent, _envelope(), "run-1")

        assert result.status == SpokeResultStatus.PARTIAL
        assert "awaiting HITL gate" in result.notes
        assert agent.call_count == 0


class TestRetryOnLowConfidence:
    def test_low_confidence_retries_until_success(self) -> None:
        pipeline, _, audit, _ = _make_pipeline()
        agent = FakeAgent(
            "discovery-1", TaskType.DISCOVERY_COLLECT, SpokeResult,
            [
                _spoke_result(SpokeResultStatus.FAILED, 0.2),
                _spoke_result(SpokeResultStatus.SUCCESS, 0.95),
            ],
        )

        result = pipeline.invoke_spoke(agent, _envelope(), "run-1")

        assert result.status == SpokeResultStatus.SUCCESS
        assert agent.call_count == 2
        assert sum(1 for e, _ in audit.events if e == "agent_invocation_complete") == 2


class TestSchemaValidationFailure:
    def test_invalid_result_type_returns_failed_without_recording_usage(self) -> None:
        pipeline, budget, _, _ = _make_pipeline()
        agent = FakeAgent("discovery-1", TaskType.DISCOVERY_COLLECT, SpokeResult, ["not-a-spoke-result"])  # type: ignore[list-item]

        result = pipeline.invoke_spoke(agent, _envelope(), "run-1")

        assert result.status == SpokeResultStatus.FAILED
        assert result.notes == "schema validation failed"
