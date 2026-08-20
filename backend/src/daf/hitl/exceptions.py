"""HITL broker-specific exceptions."""

from __future__ import annotations


class GateAlreadyDecidedError(Exception):
    """Raised by `decide()` when the ticket is not `PENDING` — no
    double-deciding a resolved ticket (design.md Algorithm 3 preconditions).
    """

    def __init__(self, ticket_id: str, current_status: str) -> None:
        self.ticket_id = ticket_id
        self.current_status = current_status
        super().__init__(f"GateTicket {ticket_id!r} is already {current_status}, cannot decide again")
