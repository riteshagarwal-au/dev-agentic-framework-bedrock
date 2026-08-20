"""Helpers for converting between Pydantic-model JSON-mode dicts and
DynamoDB-compatible item dicts.

DynamoDB's Python SDK (boto3) does not accept native `float` values (it
requires `decimal.Decimal` for any numeric type that isn't a plain int),
so every write must recursively convert floats to `Decimal` and every read
must convert them back so the Pydantic model reconstruction sees plain
JSON-compatible types again.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def to_dynamodb_item(value: Any) -> Any:
    """Recursively convert `float` values to `Decimal` for DynamoDB writes."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: to_dynamodb_item(val) for key, val in value.items()}
    if isinstance(value, list):
        return [to_dynamodb_item(val) for val in value]
    return value


def from_dynamodb_item(value: Any) -> Any:
    """Recursively convert `Decimal` values back to `float`/`int` after a
    DynamoDB read, so Pydantic model validation sees plain JSON types.
    """
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: from_dynamodb_item(val) for key, val in value.items()}
    if isinstance(value, list):
        return [from_dynamodb_item(val) for val in value]
    return value
