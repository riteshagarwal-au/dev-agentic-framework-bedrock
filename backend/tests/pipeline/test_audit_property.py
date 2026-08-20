"""Property test for exactly-once audit per invocation (Task 10.7, Property 5).

For every completed `agent.execute` call (success or failure), exactly one
`agent_invocation_complete` audit event exists with a matching traceId.
"""

from hypothesis import given
from hypothesis import strategies as st

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
from daf.models.enums import ArtifactKind, ArtifactLocationKind, SpokeResultStatus, TaskType
from daf.models.envelope import SpokeResult, TaskEnvelope
from daf.persistence.gate_ticket_repository import GateTicketRepository
from daf.persistence.run_counters_repository import RunCountersRepository
from daf.persistence.run_state_repository import RunStateRepository
from daf.pipeline.pipeline import HookPipeline, InMemoryAttemptStateStore
from tests.budget.fakes import FakeRunConfigProvider
from tests.hitl.fakes import FakePortalNotifier, FakeStepFunctionsClient
from tests.persistence.fakes import FakeDynamoDBTable
from tests.pipeline.fakes import (
    FakeAgent,
    FakeAuditLog,
    FakeGateResolver,
    FakeMemoryManager,
    FakeOpusGate,
    FakeTokenEstimator,
)


def _ref() -> ArtifactRef:
    return ArtifactRef(
        artifactId="a1", location="s3://bucket/key", locationKind=ArtifactLocationKind.S3_URI, kind=ArtifactKind.OTHER
    )


def _envelope(trace_id: str) -> TaskEnvelope:
    return TaskEnvelope(task="discover-inventory", inputs={"src": _ref()}, traceId=trace_id)


def _result(status: SpokeResultStatus, confidence: float) -> SpokeResult:
    return SpokeResult(output=_ref(), confidence=confidence, tokensUsed={"tokensIn": 1, "tokensOut": 1}, status=status)


@given(
    confidences=st.lists(st.floats(min_value=0.0, max_value=1.0, allow_nan=False), min_size=1, max_size=4)
)
def test_exactly_one_audit_event_per_completed_invocation(confidences: list[float]) -> None:
    """Each retry loop through invoke_spoke's INVOCATION step must produce
    exactly one `agent_invocation_complete` audit write per attempt — never
    zero (silently dropped) and never more than one (duplicated).
    """
    ceiling = BudgetCeiling(
        maxTotalTokens=1_000_000, maxCostUsd=1_000_000.0, maxWallClockMs=1_000_000_000,
        maxSteps=1_000_000, maxOpusInvocations=1_000_000,
    )
    counters_repo = RunCountersRepository(FakeDynamoDBTable(key_name="runId"))
    counters_repo.initialize("run-1")
    budget = CostBudgetHook(
        run_counters_repo=counters_repo,
        run_config_provider=FakeRunConfigProvider(ceiling),
        kill_switch_store=InMemoryKillSwitchStore(),
        idempotency_store=InMemoryIdempotencyStore(),
        step_history_store=InMemoryStepHistoryStore(),
        failure_counter_store=InMemoryFailureCounterStore(1_000_000),
    )
    hitl = HitlApprovalBroker(
        GateTicketRepository(FakeDynamoDBTable(key_name="ticketId")),
        RunStateRepository(FakeDynamoDBTable(key_name="runId")),
        FakeStepFunctionsClient(),
        FakePortalNotifier(),
        FakeAuditLog(),
    )
    audit = FakeAuditLog()
    pipeline = HookPipeline(
        cost_budget_hook=budget,
        hitl_broker=hitl,
        token_estimator=FakeTokenEstimator(),
        gate_resolver=FakeGateResolver(None),
        attempt_state_store=InMemoryAttemptStateStore(),
        audit_log=audit,
        memory_manager=FakeMemoryManager(),
        opus_gate_for_router=FakeOpusGate(),
    )

    # Force success on the final attempt so the retry loop always terminates.
    results = [_result(SpokeResultStatus.FAILED, c) for c in confidences[:-1]] + [
        _result(SpokeResultStatus.SUCCESS, 0.99)
    ]
    agent = FakeAgent("discovery-1", TaskType.DISCOVERY_COLLECT, SpokeResult, results)

    pipeline.invoke_spoke(agent, _envelope("trace-x"), "run-1")

    complete_events = [payload for event, payload in audit.events if event == "agent_invocation_complete"]
    assert len(complete_events) == agent.call_count
    assert all(payload["traceId"] == "trace-x" for payload in complete_events)
