"""Lambda entrypoint functions referenced directly by the Terraform `portal-api` module
(each API Gateway route's Lambda handler is `daf.portal_api.lambda_entrypoints.<name>`).

Dependencies are built once per Lambda execution environment (module import time / cold
start), then reused across warm invocations — the standard Lambda "init outside the handler"
pattern.
"""

from __future__ import annotations

from typing import Any

from daf.portal_api.handlers import (
    decide_gate_handler,
    get_run_status_handler,
    list_pending_gates_handler,
    start_run_handler,
)
from daf.portal_api.wiring import build_hitl_broker, build_supervisor

_supervisor = build_supervisor()
_hitl_broker = build_hitl_broker()


def start_run(event: dict, context: Any) -> dict:
    return start_run_handler(event, context, supervisor=_supervisor)


def get_run_status(event: dict, context: Any) -> dict:
    return get_run_status_handler(event, context, supervisor=_supervisor)


def list_pending_gates(event: dict, context: Any) -> dict:
    return list_pending_gates_handler(event, context, hitl_broker=_hitl_broker)


def decide_gate(event: dict, context: Any) -> dict:
    return decide_gate_handler(event, context, hitl_broker=_hitl_broker)
