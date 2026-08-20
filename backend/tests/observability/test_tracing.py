"""Task 16.4: tracing tests using an in-memory span exporter."""

from __future__ import annotations

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from daf.models.types import RunId, TraceId
from daf.observability.tracing import configure_tracing, start_run_span


def test_start_run_span_sets_trace_id_attribute() -> None:
    exporter = InMemorySpanExporter()
    configure_tracing("daf-test", exporter=exporter)

    trace_id = TraceId("trace-123")
    run_id = RunId("run-456")

    with start_run_span(trace_id, run_id):
        pass

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.attributes["trace_id"] == "trace-123"
    assert span.attributes["run_id"] == "run-456"


def test_start_run_span_propagates_trace_id_to_child_spans() -> None:
    exporter = InMemorySpanExporter()
    configure_tracing("daf-test", exporter=exporter)

    trace_id = TraceId("trace-789")
    run_id = RunId("run-000")

    from daf.observability.tracing import _get_tracer

    tracer = _get_tracer()
    with start_run_span(trace_id, run_id) as parent_span:
        with tracer.start_as_current_span("child") as child_span:
            child_span.set_attribute("trace_id", str(trace_id))

    spans = exporter.get_finished_spans()
    assert len(spans) == 2

    child = next(s for s in spans if s.name == "child")
    parent = next(s for s in spans if s.name == "daf.run")

    # child's parent span id matches the parent span's own span id.
    assert child.parent.span_id == parent.context.span_id
    assert child.attributes["trace_id"] == "trace-789"
    # Same OTel trace across parent/child confirms context propagation.
    assert child.context.trace_id == parent.context.trace_id
