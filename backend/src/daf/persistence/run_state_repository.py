"""RunStateRepository — idempotent per-step-boundary persistence for
`RunState` (Task 5.2).

Design ref: design.md Data Models "Model 1: RunConfig/RunState"; Algorithm 4
postconditions; Requirements 8.1, 8.5 (run resumability, Property 8).

Idempotency strategy: a write is a `PutItem` keyed by `runId`, guarded by a
`ConditionExpression` that only allows the write if either (a) no item
exists yet for this `runId`, or (b) the stored `currentStepIndex` is
strictly less than the incoming `RunState.current_step_index`. This makes
re-applying the same step-boundary write (e.g. a retried Lambda
invocation) a no-op rather than corrupting state, and prevents an
out-of-order/stale write from ever regressing `currentStepIndex` — the
property Requirement 8.5/"Property 8: Run resumability" depends on.
"""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError

from daf.models.run import RunState
from daf.persistence import DynamoDBTableProtocol
from daf.persistence.serialization import from_dynamodb_item, to_dynamodb_item


class RunStateRepository:
    """Persists and retrieves `RunState` with idempotent step-boundary writes."""

    def __init__(self, table: DynamoDBTableProtocol) -> None:
        self._table = table

    def save(self, run_state: RunState) -> bool:
        """Idempotently persist `run_state` at its `current_step_index` boundary.

        Returns:
            True if the write was applied, False if it was skipped because
            an equal-or-later step boundary was already persisted (i.e.
            this was a duplicate/stale/out-of-order write).
        """
        item = to_dynamodb_item(run_state.model_dump(by_alias=True, mode="json"))
        item["runId"] = run_state.run_id
        item["currentStepIndex"] = run_state.current_step_index
        try:
            self._table.put_item(
                Item=item,
                ConditionExpression=(
                    "attribute_not_exists(runId) OR currentStepIndex < :new_index"
                ),
                ExpressionAttributeValues={":new_index": run_state.current_step_index},
            )
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise

    def get(self, run_id: str) -> RunState | None:
        """Fetch and reconstruct the `RunState` for `run_id`, or `None` if absent."""
        response: dict[str, Any] = self._table.get_item(Key={"runId": run_id})
        item = response.get("Item")
        if item is None:
            return None
        return RunState.model_validate(from_dynamodb_item(item))

    def update_status(self, run_id: str, status: str) -> None:
        """Update only `RunState.status` (e.g. RUNNING <-> AWAITING_HITL <-> HALTED).

        Unlike `save`, this is not step-boundary guarded — a HITL gate
        transition changes status without advancing `currentStepIndex`, so
        the step-boundary idempotency check in `save` would incorrectly
        reject it.
        """
        self._table.update_item(
            Key={"runId": run_id},
            UpdateExpression="SET #status = :status",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":status": status},
        )
