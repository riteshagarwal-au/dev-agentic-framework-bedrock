"""Property test for no unapproved state-changing action (Task 9.5, Property 1).

For all 7 HitlGateType values, no corresponding action occurs unless a
GateTicket with matching gateType and status=APPROVED exists for that run,
recorded before the action's timestamp. Simulated here by modeling "the
action" as a callback that is only permitted to run after `decide()`
approves the specific ticket that gated it.
"""

from hypothesis import given
from hypothesis import strategies as st

from daf.hitl.broker import HitlApprovalBroker
from daf.models.common import ApprovalContext
from daf.models.enums import GateTicketStatus, HitlGateType
from daf.persistence.gate_ticket_repository import GateTicketRepository
from daf.persistence.run_state_repository import RunStateRepository
from tests.hitl.fakes import FakeAuditLog, FakePortalNotifier, FakeStepFunctionsClient
from tests.persistence.fakes import FakeDynamoDBTable


def _make_broker() -> HitlApprovalBroker:
    gate_tickets = GateTicketRepository(FakeDynamoDBTable(key_name="ticketId"))
    run_state = RunStateRepository(FakeDynamoDBTable(key_name="runId"))
    return HitlApprovalBroker(
        gate_tickets, run_state, FakeStepFunctionsClient(), FakePortalNotifier(), FakeAuditLog()
    )


def _perform_gated_action(broker: HitlApprovalBroker, ticket_id: str) -> bool:
    """Only "performs the action" (returns True) if the ticket is APPROVED."""
    ticket = broker._tickets.get(ticket_id)
    return ticket is not None and ticket.status == GateTicketStatus.APPROVED


@given(
    gate=st.sampled_from(list(HitlGateType)),
    decision=st.sampled_from([GateTicketStatus.APPROVED, GateTicketStatus.REJECTED]),
)
def test_action_only_proceeds_when_ticket_is_approved(gate: HitlGateType, decision: GateTicketStatus) -> None:
    broker = _make_broker()
    ticket_id = broker.raise_gate(gate, "run-1", ApprovalContext(summary="do the thing"))

    # Before any decision, the action must never be permitted.
    assert _perform_gated_action(broker, ticket_id) is False

    broker.decide(ticket_id, decision, approver="user-1")

    action_permitted = _perform_gated_action(broker, ticket_id)
    assert action_permitted == (decision == GateTicketStatus.APPROVED)
