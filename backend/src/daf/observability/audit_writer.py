"""Structured audit event writer with trace ID correlation (Task 16.2).

Satisfies the existing `AuditLog` Protocol used by `HookPipeline`
(`daf/pipeline/pipeline.py`), `Supervisor` (`daf/supervisor/supervisor.py`)
and `HitlApprovalBroker` (`daf/hitl/broker.py`):

    class AuditLog(Protocol):
        def write(self, event: str, payload: dict) -> None: ...

`JsonAuditLogWriter` is a concrete implementation of that same shape,
writing one JSON object per line to an injected sink.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable


class JsonAuditLogWriter:
    """Concrete `AuditLog` (see `daf.pipeline.pipeline.AuditLog`) that
    writes structured JSON-lines audit events to an injected sink.

    Each `write()` call produces exactly one JSON line — no batching or
    deduplication (idempotency-key dedup is a separate concern, handled by
    `CostBudgetHook`/`IdempotencyStore`, Task 8.2).
    """

    def __init__(self, sink: Callable[[str], None]) -> None:
        self._sink = sink

    def write(self, event: str, payload: dict) -> None:
        record: dict[str, Any] = {
            "event_type": event,
            "trace_id": payload.get("traceId") or payload.get("trace_id"),
            "run_id": payload.get("runId") or payload.get("run_id"),
            "agent_id": payload.get("agentId") or payload.get("agent_id"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        self._sink(json.dumps(record))


def list_sink(target: list[str]) -> Callable[[str], None]:
    """Convenience sink factory: appends each written line to `target`."""

    def _append(line: str) -> None:
        target.append(line)

    return _append


def reconstruct_sequence(json_lines: list[str], trace_id: str | None = None) -> list[str]:
    """Reconstruct the ordered list of `event_type`s from JSON-lines audit
    records, optionally filtered to a single `trace_id` (Task 16.5).

    Filtering by `trace_id` proves the audit log can be used to
    reconstruct a *specific run* even when the sink contains interleaved
    events from other trace IDs.
    """
    events: list[str] = []
    for line in json_lines:
        record = json.loads(line)
        if trace_id is not None and record.get("trace_id") != trace_id:
            continue
        events.append(record["event_type"])
    return events
