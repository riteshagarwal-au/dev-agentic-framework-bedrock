"""Structured audit event writer tests (Task 16.2 + 16.4)."""

from __future__ import annotations

import json

from daf.observability.audit_writer import JsonAuditLogWriter, list_sink


def test_write_produces_valid_json_with_required_fields() -> None:
    sink: list[str] = []
    writer = JsonAuditLogWriter(list_sink(sink))

    writer.write("run_started", {"runId": "run-1", "traceId": "trace-1"})

    assert len(sink) == 1
    record = json.loads(sink[0])
    assert record["event_type"] == "run_started"
    assert record["trace_id"] == "trace-1"
    assert record["run_id"] == "run-1"
    assert "timestamp" in record
    assert record["payload"] == {"runId": "run-1", "traceId": "trace-1"}


def test_write_includes_agent_id_when_present() -> None:
    sink: list[str] = []
    writer = JsonAuditLogWriter(list_sink(sink))

    writer.write(
        "agent_invocation_complete",
        {"runId": "run-1", "agentId": "discovery", "status": "SUCCESS", "traceId": "trace-1"},
    )

    record = json.loads(sink[0])
    assert record["agent_id"] == "discovery"


def test_n_calls_produce_exactly_n_lines() -> None:
    sink: list[str] = []
    writer = JsonAuditLogWriter(list_sink(sink))

    for i in range(5):
        writer.write("run_started", {"runId": f"run-{i}", "traceId": f"trace-{i}"})

    assert len(sink) == 5
    for i, line in enumerate(sink):
        record = json.loads(line)
        assert record["run_id"] == f"run-{i}"
