"""OpenTelemetry tracing setup (Task 16.1).

design.md's production target for trace export is CloudWatch/X-Ray
(Component "Observability & audit trail"). Wiring a real AWS exporter
dependency is out of scope here — `configure_tracing` defaults to a
`ConsoleSpanExporter` (or an injected exporter, e.g. `InMemorySpanExporter`
for tests) so this module is usable/testable without any AWS dependency.

This module deliberately does NOT get wired into `pipeline.py` /
`supervisor.py` — it is a standalone, ready-to-use helper. A future task
can wrap `Supervisor`/`HookPipeline`/agent-invocation call sites with
`start_run_span(...)`.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import Span, Tracer

from daf.models.types import RunId, TraceId

_TRACER_NAME = "daf"
_provider: TracerProvider | None = None


def configure_tracing(service_name: str, exporter: SpanExporter | None = None) -> TracerProvider:
    """Set up a `TracerProvider` for `service_name`.

    `exporter` defaults to `ConsoleSpanExporter` (Phase 1 default). Pass an
    `InMemorySpanExporter` in tests to capture finished spans for
    assertions, or a real OTLP/CloudWatch/X-Ray exporter in production.

    The provider is stored module-locally (not only via OTel's
    process-global `trace.set_tracer_provider`, which can only be set
    once per process) so repeated calls — e.g. across tests — reliably
    take effect.
    """
    global _provider
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter or ConsoleSpanExporter()))
    _provider = provider
    try:
        trace.set_tracer_provider(provider)
    except Exception:  # pragma: no cover - defensive, OTel warns not raises
        pass
    return provider


def _get_tracer() -> Tracer:
    if _provider is not None:
        return _provider.get_tracer(_TRACER_NAME)
    return trace.get_tracer(_TRACER_NAME)


@contextmanager
def start_run_span(trace_id: TraceId, run_id: RunId, name: str = "daf.run") -> Iterator[Span]:
    """Start a span tagged with `trace_id`/`run_id` as span attributes.

    Usable as `with start_run_span(trace_id, run_id):` around
    Supervisor/hook-pipeline/agent invocation code. Child spans started
    within this context automatically become children of this span, so
    the `trace_id` attribute set here is available on the run's whole
    span tree (via the parent-child span relationship), not just this
    single span.
    """
    tracer = _get_tracer()
    with tracer.start_as_current_span(name) as span:
        span.set_attribute("trace_id", str(trace_id))
        span.set_attribute("run_id", str(run_id))
        yield span
