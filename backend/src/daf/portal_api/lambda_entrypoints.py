"""Lambda entrypoint functions referenced directly by the Terraform `portal-api` module
(each API Gateway route's Lambda handler is `daf.portal_api.lambda_entrypoints.<name>`).

Dependencies are built once per Lambda execution environment (module import time / cold
start), then reused across warm invocations — the standard Lambda "init outside the handler"
pattern.
"""

from __future__ import annotations

import json
from typing import Any

from daf.models.run import RunConfig
from daf.portal_api.handlers import (
    decide_gate_handler,
    get_run_status_handler,
    list_pending_gates_handler,
    start_run_handler,
)
from daf.portal_api.wiring import (
    build_hitl_broker,
    build_supervisor,
    get_run_id_for_ticket,
    persist_budget_ceiling,
    trigger_run_worker,
)

_supervisor = build_supervisor()
_hitl_broker = build_hitl_broker()


def start_run(event: dict, context: Any) -> dict:
    response = start_run_handler(event, context, supervisor=_supervisor)
    if response["statusCode"] == 200:
        run_config = RunConfig.model_validate(json.loads(event.get("body") or "{}"))
        persist_budget_ceiling(run_config.run_id, run_config.budget_ceiling)
        trigger_run_worker(run_config.run_id)
    return response


def get_run_status(event: dict, context: Any) -> dict:
    return get_run_status_handler(event, context, supervisor=_supervisor)


def list_pending_gates(event: dict, context: Any) -> dict:
    return list_pending_gates_handler(event, context, hitl_broker=_hitl_broker)


def decide_gate(event: dict, context: Any) -> dict:
    response = decide_gate_handler(event, context, hitl_broker=_hitl_broker)
    if response["statusCode"] == 200:
        ticket_id = json.loads(event.get("body") or "{}").get("ticketId")
        run_id = get_run_id_for_ticket(ticket_id) if ticket_id else None
        if run_id:
            trigger_run_worker(run_id)
    return response
