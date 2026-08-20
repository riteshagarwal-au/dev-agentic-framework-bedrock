"""Unit tests for the Cost/Budget Counter Hook (Tasks 8.9 consecutive
failures, plus general pre_check/record_usage/kill-switch coverage).
"""

from daf.budget.hook import CostBudgetHook
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


def _make_hook(ceiling: BudgetCeiling) -> tuple[CostBudgetHook, RunCountersRepository, InMemoryKillSwitchStore]:
    counters_repo = RunCountersRepository(FakeDynamoDBTable(key_name="runId"))
    kill_switch = InMemoryKillSwitchStore()
    hook = CostBudgetHook(
        run_counters_repo=counters_repo,
        run_config_provider=FakeRunConfigProvider(ceiling),
        kill_switch_store=kill_switch,
        idempotency_store=InMemoryIdempotencyStore(),
        step_history_store=InMemoryStepHistoryStore(),
        failure_counter_store=InMemoryFailureCounterStore(MAX_CONSECUTIVE_FAILURES),
    )
    return hook, counters_repo, kill_switch


def _generous_ceiling() -> BudgetCeiling:
    return BudgetCeiling(
        maxTotalTokens=1_000_000,
        maxCostUsd=100.0,
        maxWallClockMs=3_600_000,
        maxSteps=100,
        maxOpusInvocations=1,
    )


class TestPreCheck:
    def test_ok_within_all_ceilings(self) -> None:
        hook, counters_repo, _ = _make_hook(_generous_ceiling())
        counters_repo.initialize("run-1")
        assert hook.pre_check("run-1", estimated_tokens=100).status == DecisionStatus.OK

    def test_halts_when_kill_switch_active(self) -> None:
        hook, counters_repo, kill_switch = _make_hook(_generous_ceiling())
        counters_repo.initialize("run-1")
        kill_switch.set_active("run-1", True)
        decision = hook.pre_check("run-1", estimated_tokens=1)
        assert decision.status == DecisionStatus.HALT
        assert "kill switch" in decision.reason

    def test_halts_when_token_ceiling_exceeded(self) -> None:
        ceiling = _generous_ceiling().model_copy(update={"max_total_tokens": 10})
        hook, counters_repo, _ = _make_hook(ceiling)
        counters_repo.initialize("run-1")
        decision = hook.pre_check("run-1", estimated_tokens=100)
        assert decision.status == DecisionStatus.HALT
        assert "token" in decision.reason

    def test_halts_when_step_ceiling_exceeded(self) -> None:
        ceiling = _generous_ceiling().model_copy(update={"max_steps": 0})
        hook, counters_repo, _ = _make_hook(ceiling)
        counters_repo.initialize("run-1")
        decision = hook.pre_check("run-1", estimated_tokens=1)
        assert decision.status == DecisionStatus.HALT
        assert "step" in decision.reason


class TestOpusGate:
    def test_allowed_under_ceiling(self) -> None:
        hook, counters_repo, _ = _make_hook(_generous_ceiling())
        counters_repo.initialize("run-1")
        assert hook.check_opus_gate("run-1").status == GateStatus.ALLOWED

    def test_denied_once_ceiling_reached(self) -> None:
        hook, counters_repo, _ = _make_hook(_generous_ceiling())
        counters_repo.initialize("run-1")
        hook.record_usage(
            "run-1", "agent-1", tokens_in=1, tokens_out=1, wall_clock_ms=1,
            idempotency_key="k1", spoke_result_status=SpokeResultStatus.SUCCESS,
            tool_call_signature="sig-1", progressed=True, opus_invocation=True,
        )
        assert hook.check_opus_gate("run-1").status == GateStatus.DENIED


class TestRecordUsageIdempotency:
    def test_duplicate_key_is_a_no_op(self) -> None:
        hook, counters_repo, _ = _make_hook(_generous_ceiling())
        counters_repo.initialize("run-1")

        hook.record_usage(
            "run-1", "agent-1", tokens_in=100, tokens_out=50, wall_clock_ms=10,
            idempotency_key="same-key", spoke_result_status=SpokeResultStatus.SUCCESS,
            tool_call_signature="sig-1", progressed=True,
        )
        counters_after_first = counters_repo.get("run-1")

        hook.record_usage(
            "run-1", "agent-1", tokens_in=100, tokens_out=50, wall_clock_ms=10,
            idempotency_key="same-key", spoke_result_status=SpokeResultStatus.SUCCESS,
            tool_call_signature="sig-1", progressed=True,
        )
        counters_after_duplicate = counters_repo.get("run-1")

        assert counters_after_duplicate == counters_after_first


class TestConsecutiveFailuresCircuitBreaker:
    def test_trips_kill_switch_after_threshold_consecutive_failures(self) -> None:
        hook, counters_repo, kill_switch = _make_hook(_generous_ceiling())
        counters_repo.initialize("run-1")

        for i in range(MAX_CONSECUTIVE_FAILURES):
            hook.record_usage(
                "run-1", "agent-1", tokens_in=1, tokens_out=1, wall_clock_ms=1,
                idempotency_key=f"key-{i}", spoke_result_status=SpokeResultStatus.FAILED,
                tool_call_signature=f"sig-{i}", progressed=True,
            )

        assert kill_switch.is_active("run-1") is True

    def test_reset_by_intervening_success(self) -> None:
        hook, counters_repo, kill_switch = _make_hook(_generous_ceiling())
        counters_repo.initialize("run-1")

        hook.record_usage(
            "run-1", "agent-1", tokens_in=1, tokens_out=1, wall_clock_ms=1,
            idempotency_key="key-0", spoke_result_status=SpokeResultStatus.FAILED,
            tool_call_signature="sig-0", progressed=True,
        )
        hook.record_usage(
            "run-1", "agent-1", tokens_in=1, tokens_out=1, wall_clock_ms=1,
            idempotency_key="key-1", spoke_result_status=SpokeResultStatus.SUCCESS,
            tool_call_signature="sig-1", progressed=True,
        )
        for i in range(2, 2 + MAX_CONSECUTIVE_FAILURES - 1):
            hook.record_usage(
                "run-1", "agent-1", tokens_in=1, tokens_out=1, wall_clock_ms=1,
                idempotency_key=f"key-{i}", spoke_result_status=SpokeResultStatus.FAILED,
                tool_call_signature=f"sig-{i}", progressed=True,
            )

        assert kill_switch.is_active("run-1") is False
