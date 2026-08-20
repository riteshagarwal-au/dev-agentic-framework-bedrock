"""Task 16.5: integration test reconstructing a full run from the audit
log alone.

Event type strings reused verbatim from what `pipeline.py`/`hitl/broker.py`/
`supervisor.py` already emit: `run_started`, `agent_invocation_complete`,
`hitl_gate_raised`, `hitl_gate_decided`, `run_killed` (grepped from
existing `_audit.write(...)` call sites).
"""

from __future__ import annotations

from daf.observability.audit_writer import JsonAuditLogWriter, list_sink, reconstruct_sequence


def test_reconstruct_sequence_from_audit_log_correlated_by_trace_id() -> None:
    sink: list[str] = []
    writer = JsonAuditLogWriter(list_sink(sink))

    trace_id = "trace-abc"
    other_trace_id = "trace-xyz"

    # Interleave events from a different trace_id to prove correlation,
    # not naive ordering, is what the reconstruction relies on.
    writer.write("run_started", {"runId": "run-1", "traceId": other_trace_id})

    writer.write("run_started", {"runId": "run-9", "traceId": trace_id})
    writer.write(
        "agent_invocation_complete",
        {"runId": "run-9", "agentId": "discovery", "status": "SUCCESS", "traceId": trace_id},
    )
    writer.write("run_started", {"runId": "run-1", "traceId": other_trace_id})
    writer.write(
        "agent_invocation_complete",
        {"runId": "run-9", "agentId": "security", "status": "SUCCESS", "traceId": trace_id},
    )
    writer.write("hitl_gate_raised", {"runId": "run-9", "traceId": trace_id})
    writer.write("agent_invocation_complete", {"runId": "run-1", "traceId": other_trace_id})
    writer.write("hitl_gate_decided", {"runId": "run-9", "traceId": trace_id})
    writer.write("run_killed", {"runId": "run-9", "traceId": trace_id})

    reconstructed = reconstruct_sequence(sink, trace_id=trace_id)

    assert reconstructed == [
        "run_started",
        "agent_invocation_complete",
        "agent_invocation_complete",
        "hitl_gate_raised",
        "hitl_gate_decided",
        "run_killed",
    ]
