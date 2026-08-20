"""Per-agent metrics recording tests (Task 16.4)."""

from __future__ import annotations

from daf.models.types import AgentId, RunId, TraceId
from daf.observability.metrics import InMemoryMetricsRecorder


def test_record_invocation_stores_queryable_record() -> None:
    recorder = InMemoryMetricsRecorder()

    recorder.record_invocation(
        agent_id=AgentId("discovery"),
        run_id=RunId("run-1"),
        trace_id=TraceId("trace-1"),
        latency_ms=123.4,
        tokens_in=100,
        tokens_out=50,
        estimated_cost_usd=0.01,
        escalation_occurred=False,
        tool_error=False,
    )

    records = recorder.for_run(RunId("run-1"))
    assert len(records) == 1
    record = records[0]
    assert record.agent_id == "discovery"
    assert record.latency_ms == 123.4
    assert record.tokens_in == 100
    assert record.tokens_out == 50
    assert record.estimated_cost_usd == 0.01
    assert record.escalation_occurred is False
    assert record.tool_error is False


def test_multiple_calls_are_independently_retrievable() -> None:
    recorder = InMemoryMetricsRecorder()

    recorder.record_invocation(
        agent_id=AgentId("discovery"),
        run_id=RunId("run-1"),
        trace_id=TraceId("trace-1"),
        latency_ms=10.0,
        tokens_in=1,
        tokens_out=1,
        estimated_cost_usd=0.001,
        escalation_occurred=False,
        tool_error=False,
    )
    recorder.record_invocation(
        agent_id=AgentId("security"),
        run_id=RunId("run-2"),
        trace_id=TraceId("trace-2"),
        latency_ms=20.0,
        tokens_in=2,
        tokens_out=2,
        estimated_cost_usd=0.002,
        escalation_occurred=True,
        tool_error=True,
    )

    assert len(recorder.all()) == 2
    assert len(recorder.for_run(RunId("run-1"))) == 1
    assert len(recorder.for_run(RunId("run-2"))) == 1
    assert len(recorder.for_agent(AgentId("discovery"))) == 1
    assert len(recorder.for_agent(AgentId("security"))) == 1
    assert recorder.for_agent(AgentId("security"))[0].escalation_occurred is True
    assert recorder.for_agent(AgentId("security"))[0].tool_error is True
