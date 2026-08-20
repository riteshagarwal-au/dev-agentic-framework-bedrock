"""`preCheck`, `checkOpusGate`, `recordUsage`, and the circuit-breaker
triggers (Tasks 8.1-8.6).

Design ref: design.md "Algorithm 2: Cost/Budget Counter Hook — threshold
checks".
"""

from __future__ import annotations

import logging
from typing import Protocol

from daf.budget.models import BudgetDecision, DecisionStatus, GateStatus, OpusGateDecision
from daf.budget.stores import FailureCounterStore, IdempotencyStore, KillSwitchStore, StepHistoryStore
from daf.models.budget import BudgetCeiling, RunCounters
from daf.models.enums import SpokeResultStatus
from daf.persistence.run_counters_repository import RunCountersRepository

logger = logging.getLogger(__name__)

# Phase 1 hardcoded pricing (design.md: BudgetCeiling/policy constants are
# "hardcoded config in Phase 1 ... not derived or learned"). USD per token.
_COST_PER_TOKEN_IN = 0.000003
_COST_PER_TOKEN_OUT = 0.000015


class RunConfigProvider(Protocol):
    """The subset of run configuration lookup the hook depends on —
    `getRunConfig(runId).budgetCeiling` in design.md's pseudocode.
    """

    def get_budget_ceiling(self, run_id: str) -> BudgetCeiling: ...


def estimate_cost_usd(tokens_in: int, tokens_out: int) -> float:
    """`estimateCostUsd`/`computeCost` (design.md Algorithm 2) — a Phase 1
    hardcoded per-token price, not agent/model-tier-specific yet.
    """
    return tokens_in * _COST_PER_TOKEN_IN + tokens_out * _COST_PER_TOKEN_OUT


class CostBudgetHook:
    """The Cost/Budget Counter Hook: hard caps, kill switch, Opus gate, and
    the two circuit-breaker triggers (design.md Component 3).
    """

    def __init__(
        self,
        run_counters_repo: RunCountersRepository,
        run_config_provider: RunConfigProvider,
        kill_switch_store: KillSwitchStore,
        idempotency_store: IdempotencyStore,
        step_history_store: StepHistoryStore,
        failure_counter_store: FailureCounterStore,
    ) -> None:
        self._counters_repo = run_counters_repo
        self._config_provider = run_config_provider
        self._kill_switch = kill_switch_store
        self._idempotency = idempotency_store
        self._step_history = step_history_store
        self._failure_counter = failure_counter_store

    # -- Task 8.1 -----------------------------------------------------
    def pre_check(self, run_id: str, estimated_tokens: int) -> BudgetDecision:
        """Read-only / side-effect-free threshold evaluation (Requirement 4.4)."""
        if self._kill_switch.is_active(run_id):
            return BudgetDecision(status=DecisionStatus.HALT, reason="kill switch active")

        counters = self._get_counters(run_id)
        ceiling = self._config_provider.get_budget_ceiling(run_id)

        if counters.total_tokens_in + counters.total_tokens_out + estimated_tokens > ceiling.max_total_tokens:
            return BudgetDecision(status=DecisionStatus.HALT, reason="token ceiling exceeded")

        estimated_cost_for_call = estimate_cost_usd(estimated_tokens, 0)
        if counters.estimated_cost_usd + estimated_cost_for_call > ceiling.max_cost_usd:
            return BudgetDecision(status=DecisionStatus.HALT, reason="cost ceiling exceeded")

        if counters.total_wall_clock_ms > ceiling.max_wall_clock_ms:
            return BudgetDecision(status=DecisionStatus.HALT, reason="wall-clock ceiling exceeded")

        if counters.total_steps + 1 > ceiling.max_steps:
            return BudgetDecision(status=DecisionStatus.HALT, reason="step ceiling exceeded")

        return BudgetDecision(status=DecisionStatus.OK)

    # -- Task 8.3 -------------------------------------------------------
    def check_opus_gate(self, run_id: str) -> OpusGateDecision:
        """A pure budget cap in Phase 1 (design.md note): no HITL override path yet."""
        counters = self._get_counters(run_id)
        ceiling = self._config_provider.get_budget_ceiling(run_id)

        if counters.opus_invocations < ceiling.max_opus_invocations:
            return OpusGateDecision(status=GateStatus.ALLOWED)
        return OpusGateDecision(status=GateStatus.DENIED, reason="opus budget exhausted for this run")

    # -- Task 8.2/8.4/8.5 -------------------------------------------------------
    def record_usage(
        self,
        run_id: str,
        agent_id: str,
        tokens_in: int,
        tokens_out: int,
        wall_clock_ms: int,
        idempotency_key: str,
        *,
        spoke_result_status: SpokeResultStatus,
        tool_call_signature: str,
        progressed: bool,
        opus_invocation: bool = False,
    ) -> RunCounters:
        """Atomically update `RunCounters` and evaluate both circuit-breaker
        triggers (design.md Algorithm 2 `recordUsage`).

        Args:
            idempotency_key: Caller-supplied per-invocation key (source
                §12.3). A duplicate call with the same key for this
                `(run_id, agent_id)` is a no-op (Property 7).
            spoke_result_status: Feeds `detectConsecutiveFailures`.
            tool_call_signature / progressed: Feed `detectRepeatedNoProgress`.
            opus_invocation: True iff this usage came from an Opus-tier
                call, so `opusInvocations` is only ever incremented
                immediately after `checkOpusGate` returned ALLOWED
                (Property 3) — the caller is responsible for having
                called `check_opus_gate` first.
        """
        if self._idempotency.already_recorded(run_id, agent_id, idempotency_key):
            counters = self._counters_repo.get(run_id)
            assert counters is not None, f"no RunCounters found for run_id={run_id!r}"
            return counters

        counters = self._counters_repo.increment(
            run_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            wall_clock_ms=wall_clock_ms,
            steps=1,
            opus_invocations=1 if opus_invocation else 0,
            cost_usd=estimate_cost_usd(tokens_in, tokens_out),
        )
        self._idempotency.mark_recorded(run_id, agent_id, idempotency_key)

        logger.info(
            "usage_recorded",
            extra={"runId": run_id, "agentId": agent_id, "tokensIn": tokens_in, "tokensOut": tokens_out},
        )

        self._step_history.record_step(run_id, agent_id, tool_call_signature, progressed)
        self._failure_counter.record_result(run_id, agent_id, spoke_result_status)

        if self._step_history.detect_repeated_no_progress(run_id):
            self._trigger_circuit_breaker(run_id, agent_id, "repeated identical tool calls, no forward progress")

        if self._failure_counter.detect_consecutive_failures(run_id, agent_id):
            self._trigger_circuit_breaker(run_id, agent_id, "N consecutive failures for this agent")

        return counters

    # -- Task 8.6 ---------------------------------------------------------------
    def is_kill_switch_active(self, run_id: str) -> bool:
        return self._kill_switch.is_active(run_id)

    def set_kill_switch(self, run_id: str, active: bool) -> None:
        self._kill_switch.set_active(run_id, active)
        logger.warning("kill_switch_set", extra={"runId": run_id, "active": active})

    def _trigger_circuit_breaker(self, run_id: str, agent_id: str, reason: str) -> None:
        """design.md `triggerCircuitBreaker(runId, agentId, reason)` — Phase 1
        halts the run via the kill switch, the same enforcement point
        `pre_check` already checks on every call.
        """
        self.set_kill_switch(run_id, True)
        logger.warning(
            "circuit_breaker_triggered", extra={"runId": run_id, "agentId": agent_id, "reason": reason}
        )

    def _get_counters(self, run_id: str) -> RunCounters:
        counters = self._counters_repo.get(run_id)
        assert counters is not None, f"no RunCounters found for run_id={run_id!r}"
        return counters
