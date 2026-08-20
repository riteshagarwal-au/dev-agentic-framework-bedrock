"""Per-agent metrics recording (Task 16.3).

Phase 1: in-memory implementation only. Production target is CloudWatch
custom metrics (per design.md's observability component) — not wired here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from daf.models.types import AgentId, RunId, TraceId


@dataclass(frozen=True)
class InvocationMetric:
    agent_id: AgentId
    run_id: RunId
    trace_id: TraceId
    latency_ms: float
    tokens_in: int
    tokens_out: int
    estimated_cost_usd: float
    escalation_occurred: bool
    tool_error: bool


class MetricsRecorder(Protocol):
    def record_invocation(
        self,
        agent_id: AgentId,
        run_id: RunId,
        trace_id: TraceId,
        latency_ms: float,
        tokens_in: int,
        tokens_out: int,
        estimated_cost_usd: float,
        escalation_occurred: bool,
        tool_error: bool,
    ) -> None: ...


class InMemoryMetricsRecorder:
    """Reference in-memory `MetricsRecorder` — records queryable by
    `run_id`/`agent_id` for tests.
    """

    def __init__(self) -> None:
        self._records: list[InvocationMetric] = []

    def record_invocation(
        self,
        agent_id: AgentId,
        run_id: RunId,
        trace_id: TraceId,
        latency_ms: float,
        tokens_in: int,
        tokens_out: int,
        estimated_cost_usd: float,
        escalation_occurred: bool,
        tool_error: bool,
    ) -> None:
        self._records.append(
            InvocationMetric(
                agent_id=agent_id,
                run_id=run_id,
                trace_id=trace_id,
                latency_ms=latency_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                estimated_cost_usd=estimated_cost_usd,
                escalation_occurred=escalation_occurred,
                tool_error=tool_error,
            )
        )

    def all(self) -> list[InvocationMetric]:
        return list(self._records)

    def for_run(self, run_id: RunId) -> list[InvocationMetric]:
        return [r for r in self._records if r.run_id == run_id]

    def for_agent(self, agent_id: AgentId) -> list[InvocationMetric]:
        return [r for r in self._records if r.agent_id == agent_id]
