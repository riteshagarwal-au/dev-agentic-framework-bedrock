import pytest

from daf.models.enums import GateTicketStatus, RunStatus
from daf.models.types import GateTicketId, RunId, UserId
from daf.supervisor.supervisor import RunHandle
from daf.portal_api.handlers import (
    decide_gate_handler,
    get_run_status_handler,
    list_pending_gates_handler,
    start_run_handler,
)

AUTH_EVENT_REST = {"requestContext": {"authorizer": {"claims": {"sub": "user-1"}}}}
AUTH_EVENT_HTTP_JWT = {"requestContext": {"authorizer": {"jwt": {"claims": {"sub": "user-1"}}}}}
NO_AUTH_EVENTS = [
    {},
    {"requestContext": {}},
    {"requestContext": {"authorizer": {}}},
    {"requestContext": {"authorizer": {"claims": {}}}},
    {"requestContext": {"authorizer": {"jwt": {"claims": {}}}}},
]


class FakeSupervisor:
    def __init__(self) -> None:
        self.start_run_calls: list = []
        self.get_run_status_calls: list = []

    def start_run(self, run_config):
        self.start_run_calls.append(run_config)
        return RunHandle(runId=run_config.run_id, status=RunStatus.RUNNING)

    def get_run_status(self, run_id):
        self.get_run_status_calls.append(run_id)
        return RunStatus.RUNNING


class FakeHitlBroker:
    def __init__(self) -> None:
        self.get_pending_gates_calls: list = []
        self.decide_calls: list = []

    def get_pending_gates(self, run_id):
        self.get_pending_gates_calls.append(run_id)
        return []

    def decide(self, ticket_id, decision, approver):
        self.decide_calls.append((ticket_id, decision, approver))


def _run_config_payload():
    return {
        "runId": "run-1",
        "targetApp": "app-1",
        "sourceEnv": {"resourceGroup": "rg", "subscriptionId": "sub", "resourceName": "app-1-rg"},
        "targetPlatform": "ECS_FARGATE",
        "budgetCeiling": {
            "maxTotalTokens": 100000,
            "maxCostUsd": 10.0,
            "maxWallClockMs": 3600000,
            "maxSteps": 20,
            "maxOpusInvocations": 5,
        },
        "targetRepo": "riteshagarwal-au/appmigration-daf",
    }


@pytest.mark.parametrize("no_auth_event", NO_AUTH_EVENTS)
def test_start_run_handler_rejects_unauthenticated(no_auth_event):
    fake = FakeSupervisor()
    response = start_run_handler(no_auth_event, None, supervisor=fake)
    assert response["statusCode"] == 401
    assert fake.start_run_calls == []


@pytest.mark.parametrize("no_auth_event", NO_AUTH_EVENTS)
def test_get_run_status_handler_rejects_unauthenticated(no_auth_event):
    fake = FakeSupervisor()
    response = get_run_status_handler(no_auth_event, None, supervisor=fake)
    assert response["statusCode"] == 401
    assert fake.get_run_status_calls == []


@pytest.mark.parametrize("no_auth_event", NO_AUTH_EVENTS)
def test_list_pending_gates_handler_rejects_unauthenticated(no_auth_event):
    fake = FakeHitlBroker()
    response = list_pending_gates_handler(no_auth_event, None, hitl_broker=fake)
    assert response["statusCode"] == 401
    assert fake.get_pending_gates_calls == []


@pytest.mark.parametrize("no_auth_event", NO_AUTH_EVENTS)
def test_decide_gate_handler_rejects_unauthenticated(no_auth_event):
    fake = FakeHitlBroker()
    response = decide_gate_handler(no_auth_event, None, hitl_broker=fake)
    assert response["statusCode"] == 401
    assert fake.decide_calls == []


@pytest.mark.parametrize("auth_event", [AUTH_EVENT_REST, AUTH_EVENT_HTTP_JWT])
def test_start_run_handler_forwards_to_supervisor(auth_event):
    import json

    fake = FakeSupervisor()
    event = {**auth_event, "body": json.dumps(_run_config_payload())}
    response = start_run_handler(event, None, supervisor=fake)
    assert response["statusCode"] == 200
    assert len(fake.start_run_calls) == 1
    assert fake.start_run_calls[0].run_id == "run-1"
    body = json.loads(response["body"])
    assert body["runId"] == "run-1"
    assert body["status"] == "RUNNING"


@pytest.mark.parametrize("auth_event", [AUTH_EVENT_REST, AUTH_EVENT_HTTP_JWT])
def test_get_run_status_handler_forwards_to_supervisor(auth_event):
    import json

    fake = FakeSupervisor()
    event = {**auth_event, "pathParameters": {"runId": "run-1"}}
    response = get_run_status_handler(event, None, supervisor=fake)
    assert response["statusCode"] == 200
    assert fake.get_run_status_calls == [RunId("run-1")]
    body = json.loads(response["body"])
    assert body["runId"] == "run-1"
    assert body["status"] == "RUNNING"


@pytest.mark.parametrize("auth_event", [AUTH_EVENT_REST, AUTH_EVENT_HTTP_JWT])
def test_list_pending_gates_handler_forwards_to_broker(auth_event):
    fake = FakeHitlBroker()
    event = {**auth_event, "pathParameters": {"runId": "run-1"}}
    response = list_pending_gates_handler(event, None, hitl_broker=fake)
    assert response["statusCode"] == 200
    assert fake.get_pending_gates_calls == [RunId("run-1")]


@pytest.mark.parametrize("auth_event", [AUTH_EVENT_REST, AUTH_EVENT_HTTP_JWT])
def test_decide_gate_handler_forwards_ticket_decision_approver(auth_event):
    import json

    fake = FakeHitlBroker()
    event = {
        **auth_event,
        "body": json.dumps({"ticketId": "ticket-1", "decision": "APPROVED", "approver": "user-1"}),
    }
    response = decide_gate_handler(event, None, hitl_broker=fake)
    assert response["statusCode"] == 200
    assert fake.decide_calls == [
        (GateTicketId("ticket-1"), GateTicketStatus.APPROVED, UserId("user-1"))
    ]
