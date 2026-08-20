from datetime import UTC, datetime

import pytest

from daf.cicd.compensation import compensate, resume_compensation_after_approval
from daf.models.common import ApprovalContext
from daf.models.enums import GateTicketStatus, HitlGateType
from daf.models.gate import GateTicket
from daf.models.types import GateTicketId, RunId


class FakeHitlBroker:
    def __init__(self, ticket_id: str = "ticket-1") -> None:
        self.ticket_id = GateTicketId(ticket_id)
        self.raised: list[tuple] = []

    def raise_gate(self, gate, run_id, context) -> GateTicketId:
        self.raised.append((gate, run_id, context))
        return self.ticket_id


class FakeDestructiveAction:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, sequence_ref: str) -> str:
        self.calls.append(sequence_ref)
        return f"destroyed {sequence_ref}"


def _make_ticket(status: GateTicketStatus, ticket_id: str = "ticket-1") -> GateTicket:
    return GateTicket(
        ticketId=GateTicketId(ticket_id),
        runId=RunId("run-1"),
        gateType=HitlGateType.DESTRUCTIVE_ACTION,
        status=status,
        context=ApprovalContext(summary="compensation"),
        raisedAt=datetime.now(UTC),
    )


def test_compensate_raises_gate_and_does_not_execute():
    broker = FakeHitlBroker()
    destructive_action = FakeDestructiveAction()

    result = compensate(RunId("run-1"), "seq-1", broker, destructive_action)

    assert len(broker.raised) == 1
    gate, run_id, _context = broker.raised[0]
    assert gate == HitlGateType.DESTRUCTIVE_ACTION
    assert run_id == RunId("run-1")
    assert destructive_action.calls == []
    assert result.executed is False
    assert result.ticket_id == "ticket-1"


def test_resume_executes_when_approved():
    ticket = _make_ticket(GateTicketStatus.APPROVED)
    destructive_action = FakeDestructiveAction()

    result = resume_compensation_after_approval(ticket, "seq-1", destructive_action)

    assert destructive_action.calls == ["seq-1"]
    assert result.executed is True
    assert result.ticket_id == "ticket-1"


@pytest.mark.parametrize("status", [GateTicketStatus.REJECTED, GateTicketStatus.PENDING])
def test_resume_does_not_execute_when_not_approved(status):
    ticket = _make_ticket(status)
    destructive_action = FakeDestructiveAction()

    result = resume_compensation_after_approval(ticket, "seq-1", destructive_action)

    assert destructive_action.calls == []
    assert result.executed is False
