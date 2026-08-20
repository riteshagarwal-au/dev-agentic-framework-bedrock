"""Property tests for the Cost/Budget Counter Hook (Tasks 8.7, 8.8, 8.10, 8.11).

Property 2: budget caps enforced at every preCheck boundary.
Property 3: Opus is never invoked outside its gate.
Property 6: kill switch is effective.
Property 7: idempotent usage recording.
"""

from hypothesis import given
from hypothesis import strategies as st

from daf.budget.hook import CostBudgetHook, estimate_cost_usd
from daf.budget.models import DecisionStatus, GateStatus
from daf.budget.policy import MAX_CONSECUTIVE_FAILURES
from daf.budget.stores import (
    InMemoryFailureCounterStore,
    InMemoryIdempotencyStore,
    InMemoryKillSwitchStore,
    InMemoryStepHistoryStore,
)
from daf.models.budget import BudgetCeiling
from daf.models.enums import SpokeResultStatus
from daf.persistence.run_counters_repository import RunCountersRepository
from tests.budget.fakes import FakeRunConfigProvider
from tests.persistence.fakes import FakeDynamoDBTable


def _make_hook(ceiling: BudgetCeiling) -> tuple[CostBudgetHook, RunCountersRepository]:
    counters_repo = RunCountersRepository(FakeDynamoDBTable(key_name="runId"))
    hook = CostBudgetHook(
        run_counters_repo=counters_repo,
        run_config_provider=FakeRunConfigProvider(ceiling),
        kill_switch_store=InMemoryKillSwitchStore(),
        idempotency_store=InMemoryIdempotencyStore(),
        step_history_store=InMemoryStepHistoryStore(),
        failure_counter_store=InMemoryFailureCounterStore(MAX_CONSECUTIVE_FAILURES),
    )
    return hook, counters_repo


@given(
    max_total_tokens=st.integers(min_value=0, max_value=1000),
    estimated_tokens=st.integers(min_value=0, max_value=2000),
)
def test_token_ceiling_never_exceeded_at_boundary(max_total_tokens: int, estimated_tokens: int) -> None:
    """Property 2 (token dimension): preCheck HALTs iff the projected total
    would exceed the ceiling.
    """
    ceiling = BudgetCeiling(
        maxTotalTokens=max_total_tokens, maxCostUsd=1_000_000.0,
        maxWallClockMs=1_000_000_000, maxSteps=1_000_000, maxOpusInvocations=1_000_000,
    )
    hook, counters_repo = _make_hook(ceiling)
    counters_repo.initialize("run-1")

    decision = hook.pre_check("run-1", estimated_tokens=estimated_tokens)

    would_exceed = estimated_tokens > max_total_tokens
    assert decision.status == (DecisionStatus.HALT if would_exceed else DecisionStatus.OK)


@given(max_opus_invocations=st.integers(min_value=0, max_value=5))
def test_opus_never_invoked_outside_its_gate(max_opus_invocations: int) -> None:
    """Property 3: `opusInvocations` only ever increments immediately after
    `checkOpusGate` returned ALLOWED — simulated here by only calling
    `record_usage(..., opus_invocation=True)` when the gate just allowed it,
    and asserting the counter never exceeds the ceiling.
    """
    ceiling = BudgetCeiling(
        maxTotalTokens=1_000_000, maxCostUsd=1_000_000.0,
        maxWallClockMs=1_000_000_000, maxSteps=1_000_000, maxOpusInvocations=max_opus_invocations,
    )
    hook, counters_repo = _make_hook(ceiling)
    counters_repo.initialize("run-1")

    for i in range(max_opus_invocations + 3):
        gate = hook.check_opus_gate("run-1")
        if gate.status != GateStatus.ALLOWED:
            break
        hook.record_usage(
            "run-1", "agent-1", tokens_in=1, tokens_out=1, wall_clock_ms=1,
            idempotency_key=f"key-{i}", spoke_result_status=SpokeResultStatus.SUCCESS,
            tool_call_signature=f"sig-{i}", progressed=True, opus_invocation=True,
        )

    final_counters = counters_repo.get("run-1")
    assert final_counters is not None
    assert final_counters.opus_invocations <= max_opus_invocations


def test_kill_switch_blocks_every_subsequent_pre_check() -> None:
    """Property 6: once active, no subsequent preCheck for that run returns OK."""
    ceiling = BudgetCeiling(
        maxTotalTokens=1_000_000, maxCostUsd=1_000_000.0,
        maxWallClockMs=1_000_000_000, maxSteps=1_000_000, maxOpusInvocations=10,
    )
    hook, counters_repo = _make_hook(ceiling)
    counters_repo.initialize("run-1")

    assert hook.pre_check("run-1", estimated_tokens=1).status == DecisionStatus.OK
    hook.set_kill_switch("run-1", True)

    for _ in range(10):
        assert hook.pre_check("run-1", estimated_tokens=1).status == DecisionStatus.HALT


@given(
    tokens_in=st.integers(min_value=0, max_value=10_000),
    tokens_out=st.integers(min_value=0, max_value=10_000),
    call_count=st.integers(min_value=1, max_value=5),
)
def test_recording_same_idempotency_key_repeatedly_changes_counters_only_once(
    tokens_in: int, tokens_out: int, call_count: int
) -> None:
    """Property 7: calling recordUsage N times with the same idempotency key
    changes RunCounters exactly as much as calling it once.
    """
    ceiling = BudgetCeiling(
        maxTotalTokens=10_000_000, maxCostUsd=1_000_000.0,
        maxWallClockMs=1_000_000_000, maxSteps=1_000_000, maxOpusInvocations=1_000_000,
    )
    hook, counters_repo = _make_hook(ceiling)
    counters_repo.initialize("run-1")

    for _ in range(call_count):
        hook.record_usage(
            "run-1", "agent-1", tokens_in=tokens_in, tokens_out=tokens_out, wall_clock_ms=5,
            idempotency_key="fixed-key", spoke_result_status=SpokeResultStatus.SUCCESS,
            tool_call_signature="sig", progressed=True,
        )

    counters = counters_repo.get("run-1")
    assert counters is not None
    assert counters.total_tokens_in == tokens_in
    assert counters.total_tokens_out == tokens_out
    assert counters.total_steps == 1
    assert round(counters.estimated_cost_usd, 6) == round(estimate_cost_usd(tokens_in, tokens_out), 6)
