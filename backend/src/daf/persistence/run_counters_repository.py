"""RunCountersRepository — atomic increment persistence for `RunCounters`
(Task 5.3).

Design ref: design.md "Model 2: RunCounters"; Requirements 4.5, 4.6.

`increment` uses a single `UpdateItem` call with DynamoDB's `ADD` action
(an atomic, server-side numeric increment) for every counter field, so
concurrent `recordUsage` calls (Algorithm 2, Task 8.2) against the same
`runId` never lose an update to a race condition — DynamoDB serializes
`ADD` updates per item.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from daf.models.budget import RunCounters
from daf.persistence import DynamoDBTableProtocol
from daf.persistence.serialization import from_dynamodb_item


class RunCountersRepository:
    """Persists and atomically increments `RunCounters`."""

    def __init__(self, table: DynamoDBTableProtocol) -> None:
        self._table = table

    def initialize(self, run_id: str) -> None:
        """Create a zeroed `RunCounters` row for `run_id` if one doesn't exist."""
        self._table.put_item(
            Item={
                "runId": run_id,
                "totalTokensIn": 0,
                "totalTokensOut": 0,
                "totalWallClockMs": 0,
                "totalSteps": 0,
                "opusInvocations": 0,
                "estimatedCostUsd": Decimal("0"),
            },
            ConditionExpression="attribute_not_exists(runId)",
        )

    def increment(
        self,
        run_id: str,
        *,
        tokens_in: int = 0,
        tokens_out: int = 0,
        wall_clock_ms: int = 0,
        steps: int = 0,
        opus_invocations: int = 0,
        cost_usd: float = 0.0,
    ) -> RunCounters:
        """Atomically add the given deltas to `run_id`'s counters and return
        the resulting `RunCounters`. All deltas must be non-negative — this
        method only ever increases counters (design.md: "monotonically
        increasing within a run; never decremented").
        """
        for name, delta in (
            ("tokens_in", tokens_in),
            ("tokens_out", tokens_out),
            ("wall_clock_ms", wall_clock_ms),
            ("steps", steps),
            ("opus_invocations", opus_invocations),
            ("cost_usd", cost_usd),
        ):
            if delta < 0:
                raise ValueError(f"increment() delta for {name!r} must be non-negative, got {delta}")

        response: dict[str, Any] = self._table.update_item(
            Key={"runId": run_id},
            UpdateExpression=(
                "ADD totalTokensIn :ti, totalTokensOut :to, totalWallClockMs :wc, "
                "totalSteps :st, opusInvocations :oi, estimatedCostUsd :cost"
            ),
            ExpressionAttributeValues={
                ":ti": tokens_in,
                ":to": tokens_out,
                ":wc": wall_clock_ms,
                ":st": steps,
                ":oi": opus_invocations,
                ":cost": Decimal(str(cost_usd)),
            },
            ReturnValues="ALL_NEW",
        )
        attributes = response["Attributes"]
        return RunCounters.model_validate(from_dynamodb_item(attributes))

    def get(self, run_id: str) -> RunCounters | None:
        response: dict[str, Any] = self._table.get_item(Key={"runId": run_id})
        item = response.get("Item")
        if item is None:
            return None
        return RunCounters.model_validate(from_dynamodb_item(item))
