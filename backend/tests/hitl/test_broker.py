"""Unit tests for the HITL Approval Broker gate state machine (Task 9.4)."""

import pytest

from daf.hitl.broker import HitlApprovalBroker
from daf.hitl.exceptions import GateAlreadyDecidedError
from daf.models.common import ApprovalContext
from daf.models.enums import GateTicketStatus, HitlGateType, RunStatus
from daf.persistence.gate_ticket_repository import GateTicketRepository
from daf.persistence.run_state_repository import RunStateRepository
from tests.hitl.fakes import FakeAuditLog, FakePortalNotifier, FakeStepFunctionsClient
from tests.persistence.fakes import FakeDynamoDBTable


def _make_broker():
    gate_tickets = GateTicketRepository(FakeDynamoDBTable(key_name="ticketId"))
    run_state_table = FakeDynamoDBTable(key_name="runId")
    run_state = RunStateRepository(run_state_table)
    step_functions = FakeStepFunctionsClient()
    portal = FakePortalNotifier()
    audit = FakeAuditLog()
    broker = HitlApprovalBroker(gate_tickets, run_state, step_functions, portal, audit)
    return broker, gate_tickets, run_state_table, step_functions, portal, audit


class TestRaiseGate:
    def test_persists_pending_ticket_and_notifies(self) -> None:
        broker, gate_tickets, run_state_table, step_functions, portal, audit = _make_broker()

        ticket_id = broker.raise_gate(
            HitlGateType.INFRA_APPLY, "run-1", ApprovalContext(summary="apply plan")
        )

        ticket = gate_tickets.get(ticket_id)
        assert ticket is not None
        assert ticket.status == GateTicketStatus.PENDING
        assert len(portal.gate_raised) == 1
        assert any(event == "hitl_gate_raised" for event, _ in audit.events)
        assert run_state_table.get_item(Key={"runId": "run-1"})["Item"]["status"] == RunStatus.AWAITING_HITL

    def test_persisted_before_notification(self) -> None:
        """Requirement 5.7: ticket must be persisted before any notification."""
        broker, gate_tickets, _, _, portal, _ = _make_broker()
        original_create = gate_tickets.create
        order: list[str] = []

        def tracked_create(ticket):
            order.append("persist")
            return original_create(ticket)

        gate_tickets.create = tracked_create  # type: ignore[method-assign]
        original_notify = portal.notify_gate_raised

        def tracked_notify(ticket):
            order.append("notify")
            return original_notify(ticket)

        portal.notify_gate_raised = tracked_notify  # type: ignore[method-assign]

        broker.raise_gate(HitlGateType.PR_MERGE, "run-1", ApprovalContext(summary="merge PR"))

        assert order == ["persist", "notify"]


class TestDecide:
    def test_approved_resumes_run_and_sends_task_success(self) -> None:
        broker, gate_tickets, run_state_table, step_functions, _, audit = _make_broker()
        ticket_id = broker.raise_gate(HitlGateType.PR_MERGE, "run-1", ApprovalContext(summary="merge"))

        broker.decide(ticket_id, GateTicketStatus.APPROVED, approver="user-1")

        ticket = gate_tickets.get(ticket_id)
        assert ticket.status == GateTicketStatus.APPROVED
        assert ticket.approver == "user-1"
        assert run_state_table.get_item(Key={"runId": "run-1"})["Item"]["status"] == RunStatus.RUNNING
        assert len(step_functions.successes) == 1
        assert any(event == "hitl_gate_decided" for event, _ in audit.events)

    def test_rejected_halts_run_and_sends_task_failure(self) -> None:
        broker, gate_tickets, run_state_table, step_functions, portal, _ = _make_broker()
        ticket_id = broker.raise_gate(
            HitlGateType.DESTRUCTIVE_ACTION, "run-1", ApprovalContext(summary="delete resource")
        )

        broker.decide(ticket_id, GateTicketStatus.REJECTED, approver="user-1")

        ticket = gate_tickets.get(ticket_id)
        assert ticket.status == GateTicketStatus.REJECTED
        assert run_state_table.get_item(Key={"runId": "run-1"})["Item"]["status"] == RunStatus.HALTED
        assert len(step_functions.failures) == 1
        assert len(portal.run_halted) == 1

    def test_cannot_decide_an_already_decided_ticket(self) -> None:
        broker, *_ = _make_broker()
        ticket_id = broker.raise_gate(HitlGateType.KB_WRITE, "run-1", ApprovalContext(summary="write kb"))
        broker.decide(ticket_id, GateTicketStatus.APPROVED, approver="user-1")

        with pytest.raises(GateAlreadyDecidedError):
            broker.decide(ticket_id, GateTicketStatus.REJECTED, approver="user-2")


class TestGetPendingGates:
    def test_returns_only_pending_tickets_for_the_run(self) -> None:
        broker, *_ = _make_broker()
        pending_id = broker.raise_gate(HitlGateType.PLAN_FINALIZE, "run-1", ApprovalContext(summary="a"))
        decided_id = broker.raise_gate(HitlGateType.CLOUD_DEPLOY, "run-1", ApprovalContext(summary="b"))
        broker.decide(decided_id, GateTicketStatus.APPROVED, approver="user-1")

        pending = broker.get_pending_gates("run-1")

        assert [t.ticket_id for t in pending] == [pending_id]
