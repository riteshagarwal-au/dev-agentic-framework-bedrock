"""GateTicketRepository — create/read/update persistence for `GateTicket`
(Task 5.4).

Design ref: design.md "Model 3: HitlGateTicket"; Requirements 5.3, 5.7.

Requirement 5.7 ("a ticket is persisted before any notification is
sent") is enforced by call-order at the caller (Algorithm 3's `raiseGate`,
Task 9.1): this repository's `create` must be awaited/completed before the
caller sends any notification — this class itself has no notification
side effect to sequence.
"""

from __future__ import annotations

from typing import Any

from daf.models.gate import GateTicket
from daf.persistence import DynamoDBTableProtocol
from daf.persistence.serialization import from_dynamodb_item, to_dynamodb_item


class GateTicketRepository:
    """Persists and retrieves `GateTicket` records."""

    def __init__(self, table: DynamoDBTableProtocol) -> None:
        self._table = table

    def create(self, ticket: GateTicket) -> None:
        """Persist a newly raised ticket. Fails if `ticket_id` already exists,
        since a ticket ID should only ever be created once (raiseGate,
        Task 9.1).
        """
        item = to_dynamodb_item(ticket.model_dump(by_alias=True, mode="json"))
        self._table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(ticketId)",
        )

    def get(self, ticket_id: str) -> GateTicket | None:
        response: dict[str, Any] = self._table.get_item(Key={"ticketId": ticket_id})
        item = response.get("Item")
        if item is None:
            return None
        return GateTicket.model_validate(from_dynamodb_item(item))

    def update(self, ticket: GateTicket) -> None:
        """Overwrite an existing ticket (e.g. after `decide()`, Task 9.2
        transitions its status). Fails if the ticket does not already
        exist, since `update` is never used to create a new ticket.
        """
        item = to_dynamodb_item(ticket.model_dump(by_alias=True, mode="json"))
        self._table.put_item(
            Item=item,
            ConditionExpression="attribute_exists(ticketId)",
        )

    def list_by_run(self, run_id: str) -> list[GateTicket]:
        """Query all tickets for a run via the `runId` GSI (Task 5.1)."""
        response: dict[str, Any] = self._table.query(
            IndexName="runId-index",
            KeyConditionExpression="runId = :run_id",
            ExpressionAttributeValues={":run_id": run_id},
        )
        return [GateTicket.model_validate(from_dynamodb_item(item)) for item in response.get("Items", [])]
