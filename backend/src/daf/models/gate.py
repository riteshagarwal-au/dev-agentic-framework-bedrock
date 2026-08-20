"""GateTicket (design.md "Model 3: HitlGateTicket")."""

from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, Field

from daf.models.common import ApprovalContext, DafBaseModel
from daf.models.enums import GateTicketStatus, HitlGateType
from daf.models.types import GateTicketId, RunId, UserId


class GateTicket(DafBaseModel):
    """A single HITL gate request/decision record (design.md Model 3).

    `decided_at`, `approver`, and `step_functions_task_token` are optional
    because a freshly `raiseGate`d ticket (Task 9.1) has a token but no
    decision yet, while `decided_at`/`approver` only become populated once
    `decide()` (Task 9.2) resolves the ticket.
    """

    ticket_id: GateTicketId = Field(alias="ticketId")
    run_id: RunId = Field(alias="runId")
    gate_type: HitlGateType = Field(alias="gateType")
    status: GateTicketStatus = GateTicketStatus.PENDING
    context: ApprovalContext
    raised_at: datetime = Field(alias="raisedAt")
    decided_at: datetime | None = Field(default=None, alias="decidedAt")
    approver: UserId | None = None
    step_functions_task_token: str | None = Field(default=None, alias="stepFunctionsTaskToken")

    model_config = ConfigDict(extra="forbid", validate_assignment=True, populate_by_name=True)
