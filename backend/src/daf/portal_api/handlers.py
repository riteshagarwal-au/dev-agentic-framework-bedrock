"""Portal-facing Lambda handlers (Task 17.1).

Each handler is a classic AWS Lambda proxy-integration entry point:
`(event: dict, context: Any) -> dict`, returning an API-Gateway-proxy-shaped
response (`{"statusCode": int, "body": json.dumps(...), "headers": {...}}`).

Auth: for Phase 1 with Cognito, authentication is enforced by API Gateway's
Cognito (or HTTP API JWT) authorizer *before* the Lambda is ever invoked.
`_require_authenticated_claims` is a defense-in-depth check only — it
re-asserts that the authorizer actually attached non-empty claims to the
event, so that even a misconfigured/bypassed authorizer can never let an
unauthenticated request reach a run-control action (Requirement 12.4).
"""

from __future__ import annotations

import json
from typing import Any

from daf.hitl.broker import HitlApprovalBroker
from daf.models.enums import GateTicketStatus
from daf.models.run import RunConfig
from daf.models.types import GateTicketId, RunId, UserId
from daf.supervisor.supervisor import Supervisor

_JSON_HEADERS = {"Content-Type": "application/json"}


def _response(status_code: int, body: dict) -> dict:
    return {"statusCode": status_code, "headers": _JSON_HEADERS, "body": json.dumps(body)}


def _require_authenticated_claims(event: dict) -> dict | None:
    """Return the authorizer claims dict, or `None` if absent/empty.

    Supports both the REST API (Cognito user pool) authorizer shape
    (`requestContext.authorizer.claims`) and the HTTP API JWT authorizer
    shape (`requestContext.authorizer.jwt.claims`).
    """
    authorizer = event.get("requestContext", {}).get("authorizer", {}) or {}
    claims = authorizer.get("claims") or authorizer.get("jwt", {}).get("claims")
    if not claims:
        return None
    return claims


def _unauthorized_response() -> dict:
    return _response(401, {"message": "Unauthorized: no authenticated caller claims present"})


def _build_default_supervisor() -> Supervisor:
    """Real-infra wiring (DynamoDB tables, Step Functions, agent registry)
    is a deployment concern out of scope for this task — handlers always
    receive a real `Supervisor` injected by the deployed Lambda's wiring
    module, or a fake injected by tests. This default only exists to
    satisfy the DI pattern's default-parameter contract and should never
    actually be invoked in tests (tests always inject a fake).
    """
    raise NotImplementedError(
        "No default Supervisor wiring configured; inject a Supervisor instance explicitly."
    )


def _build_default_hitl_broker() -> HitlApprovalBroker:
    raise NotImplementedError(
        "No default HitlApprovalBroker wiring configured; inject an instance explicitly."
    )


def start_run_handler(event: dict, context: Any, supervisor: Supervisor | None = None) -> dict:
    claims = _require_authenticated_claims(event)
    if claims is None:
        return _unauthorized_response()

    supervisor = supervisor if supervisor is not None else _build_default_supervisor()
    payload = json.loads(event.get("body") or "{}")
    run_config = RunConfig.model_validate(payload)
    run_handle = supervisor.start_run(run_config)
    return _response(200, run_handle.model_dump(by_alias=True, mode="json"))


def get_run_status_handler(event: dict, context: Any, supervisor: Supervisor | None = None) -> dict:
    claims = _require_authenticated_claims(event)
    if claims is None:
        return _unauthorized_response()

    supervisor = supervisor if supervisor is not None else _build_default_supervisor()
    run_id = RunId(event.get("pathParameters", {})["runId"])
    status = supervisor.get_run_status(run_id)
    body = {"runId": run_id, "status": status.value}

    get_run_state = getattr(supervisor, "get_run_state", None)
    if get_run_state is not None:
        run_state = get_run_state(run_id)
        body["currentStepIndex"] = run_state.current_step_index
        body["taskGraph"] = [
            {"taskId": n.task_id, "taskType": n.task_type, "agentId": n.agent_id, "completed": n.completed}
            for n in run_state.task_graph
        ]

    return _response(200, body)


def list_pending_gates_handler(
    event: dict, context: Any, hitl_broker: HitlApprovalBroker | None = None
) -> dict:
    claims = _require_authenticated_claims(event)
    if claims is None:
        return _unauthorized_response()

    hitl_broker = hitl_broker if hitl_broker is not None else _build_default_hitl_broker()
    run_id = RunId(event.get("pathParameters", {})["runId"])
    tickets = hitl_broker.get_pending_gates(run_id)
    return _response(200, [t.model_dump(by_alias=True, mode="json") for t in tickets])


def decide_gate_handler(
    event: dict, context: Any, hitl_broker: HitlApprovalBroker | None = None
) -> dict:
    claims = _require_authenticated_claims(event)
    if claims is None:
        return _unauthorized_response()

    hitl_broker = hitl_broker if hitl_broker is not None else _build_default_hitl_broker()
    payload = json.loads(event.get("body") or "{}")
    ticket_id = GateTicketId(payload["ticketId"])
    decision = GateTicketStatus(payload["decision"])
    approver = UserId(payload["approver"])
    hitl_broker.decide(ticket_id, decision, approver)
    return _response(200, {"ticketId": ticket_id, "decision": decision.value})
