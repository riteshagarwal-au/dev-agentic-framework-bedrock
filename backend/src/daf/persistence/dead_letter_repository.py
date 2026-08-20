"""DeadLetterRecordRepository — create/list-by-run persistence for
`DeadLetterRecord` (Task 5.5).

Design ref: design.md Algorithm 4 postconditions; Requirement 8.3.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from daf.models.deadletter import DeadLetterRecord
from daf.persistence import DynamoDBTableProtocol
from daf.persistence.serialization import from_dynamodb_item, to_dynamodb_item


class DeadLetterRecordRepository:
    """Persists and retrieves `DeadLetterRecord`s for exhausted-retry failures."""

    def __init__(self, table: DynamoDBTableProtocol) -> None:
        self._table = table

    def create(
        self,
        *,
        run_id: str,
        task_envelope_ref: Any,
        error_detail: str,
        retry_count: int,
        trace_id: str,
    ) -> DeadLetterRecord:
        """Generate a new `deadLetterId` and persist the record.

        Args:
            task_envelope_ref: An `ArtifactRef` pointing at the failed
                task's envelope (never the envelope's inlined content).
        """
        record = DeadLetterRecord(
            deadLetterId=str(uuid.uuid4()),
            runId=run_id,
            taskEnvelopeRef=task_envelope_ref,
            errorDetail=error_detail,
            retryCount=retry_count,
            traceId=trace_id,
            createdAt=datetime.now(UTC),
        )
        item = to_dynamodb_item(record.model_dump(by_alias=True, mode="json"))
        self._table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(deadLetterId)",
        )
        return record

    def list_by_run(self, run_id: str) -> list[DeadLetterRecord]:
        """Query all dead-letter records for a run via the `runId` GSI (Task 5.1)."""
        response: dict[str, Any] = self._table.query(
            IndexName="runId-index",
            KeyConditionExpression="runId = :run_id",
            ExpressionAttributeValues={":run_id": run_id},
        )
        return [
            DeadLetterRecord.model_validate(from_dynamodb_item(item)) for item in response.get("Items", [])
        ]
