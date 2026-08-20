"""DynamoDB persistence layer for run state (design.md Data Models,
Task 5).

design.md "Model 1: RunConfig/RunState", "Model 2: RunCounters", "Model 3:
HitlGateTicket"; Algorithm 4 postconditions; Requirement 8.3 (dead-letter
persistence).

Shared conventions across every repository in this package:

- Each repository wraps a single `boto3.resource("dynamodb").Table(...)`
  (typed as `DynamoDBTableProtocol` below so tests can pass a stub/mock
  without requiring `moto`/live AWS access).
- Repositories never construct their own boto3 clients — the table is
  always injected, matching `CredentialsClient`'s pattern (Task 4.1) of
  taking the AWS client/resource as a constructor argument.
- All read paths reconstruct the corresponding Pydantic model from the
  raw DynamoDB item, so callers never see a raw `dict` — only validated
  domain models.
"""

from __future__ import annotations

from typing import Any, Protocol


class DynamoDBTableProtocol(Protocol):
    """The subset of `boto3.resource("dynamodb").Table(...)`'s interface
    the repositories in this package depend on. Typed as a `Protocol` so
    any object exposing these methods — the real boto3 Table resource, or
    a test stub — satisfies the type without requiring `boto3-stubs`.
    """

    def get_item(self, **kwargs: Any) -> dict[str, Any]: ...

    def put_item(self, **kwargs: Any) -> dict[str, Any]: ...

    def update_item(self, **kwargs: Any) -> dict[str, Any]: ...

    def query(self, **kwargs: Any) -> dict[str, Any]: ...
