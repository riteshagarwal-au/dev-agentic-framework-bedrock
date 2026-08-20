"""A minimal in-memory fake of `boto3.resource("dynamodb").Table(...)` used
by the persistence-layer unit tests (Task 5.6).

Only supports the exact `ConditionExpression`/`UpdateExpression` patterns
the repositories in `daf.persistence` actually use — it is not a general
DynamoDB emulator.
"""

from __future__ import annotations

from typing import Any


def _conditional_check_failed() -> Exception:
    from botocore.exceptions import ClientError

    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "conditional check failed"}},
        "PutItem",
    )


class FakeDynamoDBTable:
    def __init__(self, key_name: str, gsi_key_name: str | None = None) -> None:
        self._key_name = key_name
        self._gsi_key_name = gsi_key_name
        self._items: dict[Any, dict[str, Any]] = {}

    def get_item(self, **kwargs: Any) -> dict[str, Any]:
        key = kwargs["Key"][self._key_name]
        item = self._items.get(key)
        return {"Item": item} if item is not None else {}

    def put_item(self, **kwargs: Any) -> dict[str, Any]:
        item = kwargs["Item"]
        key = item[self._key_name]
        condition = kwargs.get("ConditionExpression")
        existing = self._items.get(key)

        if condition in (
            "attribute_not_exists(runId)",
            "attribute_not_exists(deadLetterId)",
            "attribute_not_exists(ticketId)",
        ):
            if existing is not None:
                raise _conditional_check_failed()
        elif condition == "attribute_exists(ticketId)":
            if existing is None:
                raise _conditional_check_failed()
        elif condition == "attribute_not_exists(runId) OR currentStepIndex < :new_index":
            new_index = kwargs["ExpressionAttributeValues"][":new_index"]
            if existing is not None and existing.get("currentStepIndex", -1) >= new_index:
                raise _conditional_check_failed()

        self._items[key] = dict(item)
        return {}

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        key = kwargs["Key"][self._key_name]
        values = kwargs["ExpressionAttributeValues"]
        update_expression = kwargs["UpdateExpression"]

        if update_expression.startswith("SET "):
            existing = self._items.setdefault(key, {self._key_name: key})
            names = kwargs.get("ExpressionAttributeNames", {})
            attr = update_expression.removeprefix("SET ").split("=")[0].strip()
            attr = names.get(attr, attr)
            existing[attr] = values[":status"]
            return {"Attributes": dict(existing)}

        existing = self._items.setdefault(
            key,
            {
                self._key_name: key,
                "totalTokensIn": 0,
                "totalTokensOut": 0,
                "totalWallClockMs": 0,
                "totalSteps": 0,
                "opusInvocations": 0,
                "estimatedCostUsd": 0,
            },
        )
        existing["totalTokensIn"] += values[":ti"]
        existing["totalTokensOut"] += values[":to"]
        existing["totalWallClockMs"] += values[":wc"]
        existing["totalSteps"] += values[":st"]
        existing["opusInvocations"] += values[":oi"]
        existing["estimatedCostUsd"] = existing["estimatedCostUsd"] + values[":cost"]
        return {"Attributes": dict(existing)}

    def query(self, **kwargs: Any) -> dict[str, Any]:
        run_id = kwargs["ExpressionAttributeValues"][":run_id"]
        items = [item for item in self._items.values() if item.get("runId") == run_id]
        return {"Items": items}
