"""HITL-gated compensation action (Task 14.7) — e.g. `terraform destroy` of
a just-applied module, gated behind the `DESTRUCTIVE_ACTION` HITL gate.

Design ref: design.md Algorithm 3 (HITL Gate state machine) and
`daf.hitl.broker.HitlApprovalBroker.raise_gate` (Task 9.1). `raise_gate`
returns as soon as the ticket is persisted — it does not block for the
decision (the real decision happens later via a separate `decide()` call
and Step Functions resume; see `daf.pipeline.pipeline` module docstring
for the same non-blocking design note). `compensate` therefore only
raises the gate and returns a pending result; the actual destructive
action is executed by `resume_compensation_after_approval`, which the
caller invokes only once it has confirmed (e.g. via a `GateTicketRepository`
read) that the ticket's status is `APPROVED`.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from daf.models.common import ApprovalContext
from daf.models.enums import GateTicketStatus, HitlGateType
from daf.models.gate import GateTicket
from daf.models.types import GateTicketId, RunId


class HitlBrokerProtocol(Protocol):
    def raise_gate(self, gate: HitlGateType, run_id: RunId, context: ApprovalContext) -> GateTicketId: ...


class DestructiveActionProtocol(Protocol):
    def execute(self, sequence_ref: str) -> str:
        """Perform the destructive action (e.g. `terraform destroy` of the
        just-applied module) and return a result summary string."""
        ...


class CompensationResult(BaseModel):
    executed: bool
    ticket_id: str
    detail: str


def compensate(
    run_id: RunId,
    sequence_ref: str,
    hitl_broker: HitlBrokerProtocol,
    destructive_action: DestructiveActionProtocol,
) -> CompensationResult:
    """Raise the `DESTRUCTIVE_ACTION` HITL gate for `sequence_ref` and
    return immediately, awaiting approval. `destructive_action` is accepted
    here (per this repo's expected call signature) but deliberately never
    invoked — see `resume_compensation_after_approval` for the only place
    `execute` is called, once a ticket is confirmed `APPROVED`.
    """
    ticket_id = hitl_broker.raise_gate(
        HitlGateType.DESTRUCTIVE_ACTION,
        run_id,
        ApprovalContext(summary=f"compensation (destructive action) requested for {sequence_ref}"),
    )
    return CompensationResult(
        executed=False,
        ticket_id=str(ticket_id),
        detail=f"awaiting HITL approval for destructive compensation of {sequence_ref}",
    )


def resume_compensation_after_approval(
    ticket: GateTicket, sequence_ref: str, destructive_action: DestructiveActionProtocol
) -> CompensationResult:
    """Execute the destructive compensation action, but only if `ticket`
    has already been decided `APPROVED`. Never calls `execute` for any
    other ticket status (`PENDING`, `REJECTED`, `EXPIRED`).
    """
    if ticket.status != GateTicketStatus.APPROVED:
        return CompensationResult(
            executed=False,
            ticket_id=str(ticket.ticket_id),
            detail=f"ticket {ticket.ticket_id} is {ticket.status.value}, not APPROVED: compensation not executed",
        )

    detail = destructive_action.execute(sequence_ref)
    return CompensationResult(executed=True, ticket_id=str(ticket.ticket_id), detail=detail)
