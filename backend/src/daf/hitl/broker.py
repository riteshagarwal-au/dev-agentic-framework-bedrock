"""`raiseGate` (Task 9.1), `decide` (Task 9.2), `getPendingGates` (Task 9.3).

Design ref: design.md "Algorithm 3: HITL Gate state machine".
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Protocol

from daf.hitl.exceptions import GateAlreadyDecidedError
from daf.models.common import ApprovalContext
from daf.models.enums import GateTicketStatus, HitlGateType, RunStatus
from daf.models.gate import GateTicket
from daf.models.types import GateTicketId, RunId, UserId
from daf.persistence.gate_ticket_repository import GateTicketRepository
from daf.persistence.run_state_repository import RunStateRepository

logger = logging.getLogger(__name__)


class StepFunctionsClientProtocol(Protocol):
    """The subset of the Step Functions "wait for task token" mechanism
    (Component 4) the broker depends on. Typed as a `Protocol` so tests
    can pass a stub without a live AWS Step Functions execution.
    """

    def start_execution_and_wait_for_task_token(
        self, gate: HitlGateType, run_id: RunId, ticket_id: GateTicketId
    ) -> str:
        """Start a Step Functions execution that pauses on the
        "wait for task token" pattern. Returns the task token.
        """
        ...

    def send_task_success(self, task_token: str, result: str) -> None: ...

    def send_task_failure(self, task_token: str, reason: str) -> None: ...


class PortalNotifier(Protocol):
    """The subset of portal notification (source §9) the broker depends on."""

    def notify_gate_raised(self, ticket: GateTicket) -> None: ...

    def notify_run_halted(self, run_id: RunId, reason: str) -> None: ...


class AuditLog(Protocol):
    """The subset of the audit log (source §12.2) the broker depends on."""

    def write(self, event: str, payload: dict) -> None: ...


class HitlApprovalBroker:
    """Brokers the 7 HITL gates as an explicit `PENDING -> APPROVED|REJECTED`
    state machine (design.md Algorithm 3).
    """

    def __init__(
        self,
        gate_ticket_repo: GateTicketRepository,
        run_state_repo: RunStateRepository,
        step_functions_client: StepFunctionsClientProtocol,
        portal_notifier: PortalNotifier,
        audit_log: AuditLog,
    ) -> None:
        self._tickets = gate_ticket_repo
        self._run_state = run_state_repo
        self._step_functions = step_functions_client
        self._portal = portal_notifier
        self._audit = audit_log

    # -- Task 9.1 -----------------------------------------------------
    def raise_gate(self, gate: HitlGateType, run_id: RunId, context: ApprovalContext) -> GateTicketId:
        """Persist a new `PENDING` ticket, start the durable Step Functions
        wait, and flip the run to `AWAITING_HITL`.

        Persistence happens before notification (Requirement 5.7: "a
        ticket is persisted before any notification is sent").
        """
        ticket_id = GateTicketId(str(uuid.uuid4()))
        task_token = self._step_functions.start_execution_and_wait_for_task_token(gate, run_id, ticket_id)

        ticket = GateTicket(
            ticketId=ticket_id,
            runId=run_id,
            gateType=gate,
            status=GateTicketStatus.PENDING,
            context=context,
            raisedAt=datetime.now(UTC),
            stepFunctionsTaskToken=task_token,
        )
        self._tickets.create(ticket)

        self._run_state.update_status(run_id, RunStatus.AWAITING_HITL)
        self._portal.notify_gate_raised(ticket)
        self._audit.write("hitl_gate_raised", ticket.model_dump(by_alias=True, mode="json"))

        return ticket_id

    # -- Task 9.2 -----------------------------------------------------
    def decide(self, ticket_id: GateTicketId, decision: GateTicketStatus, approver: UserId) -> None:
        """Resolve a `PENDING` ticket and resume (or halt) the paused run.

        Raises:
            GateAlreadyDecidedError: `ticket_id` is not currently `PENDING`
                (no double-deciding a resolved ticket).
        """
        if decision not in (GateTicketStatus.APPROVED, GateTicketStatus.REJECTED):
            raise ValueError(f"decide() decision must be APPROVED or REJECTED, got {decision!r}")

        ticket = self._tickets.get(ticket_id)
        if ticket is None:
            raise ValueError(f"No GateTicket found for ticket_id={ticket_id!r}")
        if ticket.status != GateTicketStatus.PENDING:
            raise GateAlreadyDecidedError(ticket_id, ticket.status.value)

        updated = ticket.model_copy(
            update={"status": decision, "decided_at": datetime.now(UTC), "approver": approver}
        )
        self._tickets.update(updated)
        self._audit.write("hitl_gate_decided", updated.model_dump(by_alias=True, mode="json"))

        if decision == GateTicketStatus.APPROVED:
            self._run_state.update_status(ticket.run_id, RunStatus.RUNNING)
            self._step_functions.send_task_success(ticket.step_functions_task_token or "", result="APPROVED")
        else:
            self._run_state.update_status(ticket.run_id, RunStatus.HALTED)
            self._step_functions.send_task_failure(
                ticket.step_functions_task_token or "", reason=f"HITL gate rejected: {ticket.gate_type}"
            )
            self._portal.notify_run_halted(ticket.run_id, f"run halted: gate {ticket.gate_type} rejected")

    # -- Task 9.3 -----------------------------------------------------
    def get_pending_gates(self, run_id: RunId) -> list[GateTicket]:
        """All tickets for `run_id` still awaiting a decision."""
        return [t for t in self._tickets.list_by_run(run_id) if t.status == GateTicketStatus.PENDING]
