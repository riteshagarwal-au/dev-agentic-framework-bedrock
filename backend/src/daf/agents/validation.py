"""Output-schema validation utility for the post-invocation hook pipeline.

design.md Algorithm 4 "Pre/Post Agent-Invocation Hook Pipeline",
post-invocation stage: "Output schema validation (Pydantic/JSON Schema)"
before the pipeline accepts a spoke agent's result.

Requirement 6.5: "AFTER a spoke agent's model call returns, the pipeline
SHALL validate the result against that agent's output schema before
accepting the result."

Requirement 6.6: "IF output schema validation fails THEN the pipeline
SHALL return a FAILED result and SHALL NOT record it as a successful
completion."

Design decision — what "schema" means here
--------------------------------------------
`SpokeResult` (Task 6.1) already fixes the shape every agent's result
must have (`output`, `confidence`, `tokensUsed`, `status`, `notes` —
Requirement 2.1 names exactly these five fields). Nothing in this
codebase defines a looser "raw agent result" shape upstream of
`SpokeResult`: the invocation stage (Task 10.2) either gets back a
`SpokeResult` directly, or a plain `dict` (e.g. an unparsed Bedrock Agents
action-group response) that the pipeline needs to validate/coerce into
one before trusting it.

So `validate_output_schema(result, schema)` is written to serve exactly
that job:

- `result` is the possibly-raw value to check — a `SpokeResult` instance,
  or a `dict` shaped like one.
- `schema` is a Pydantic model class `result` must conform to. Every
  Task 10.3 call site passes `SpokeResult` here, but the parameter is
  intentionally generic (`type[BaseModel]`, not hardcoded to
  `SpokeResult`) so a future agent whose output artifact needs a
  stricter/more specific schema of its own can reuse this exact same
  utility — there is no `SpokeResult`-specific logic baked into this
  function.

On success, the function returns a validated `schema` instance. On
failure, it raises `OutputSchemaValidationError` — a specific, well-named
exception (never a bare `pydantic.ValidationError`) so the hook pipeline
can catch precisely this failure mode and turn it into a `FAILED`
`SpokeResult` (Requirement 6.6) rather than letting an unrelated
`ValidationError` elsewhere in the call stack be mistaken for a schema
failure.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


class OutputSchemaValidationError(Exception):
    """Raised by `validate_output_schema` when `result` does not conform
    to `schema`.

    Carries the target schema's name (`schema_name`) and the underlying
    Pydantic `ValidationError`'s structured error list (`errors`, from
    `ValidationError.errors()`) as attributes — not just a formatted
    message — so the hook pipeline (Task 10.3) can log/audit the specific
    validation failures and construct a `FAILED` `SpokeResult`
    (Requirement 6.6) without re-parsing this exception's string form.
    """

    def __init__(self, schema: type[BaseModel], errors: list[dict[str, Any]]) -> None:
        self.schema_name = schema.__name__
        self.errors = errors
        summary = "; ".join(
            f"{'.'.join(str(loc) for loc in err.get('loc', ()))}: {err.get('msg', '')}"
            for err in errors
        )
        super().__init__(f"Result does not conform to {self.schema_name!r} output schema: {summary}")


def validate_output_schema(result: Any, schema: type[ModelT]) -> ModelT:
    """Validate/coerce `result` against `schema`.

    Args:
        result: The value to validate — typically a `SpokeResult`
            instance already, or a raw `dict` (e.g. a not-yet-parsed
            agent response) that should conform to `schema`'s shape once
            validated.
        schema: The Pydantic model class `result` must conform to. Every
            Task 10.3 call site passes `SpokeResult`; the parameter is
            generic so a future agent-specific output schema can reuse
            this same function (see module docstring).

    Returns:
        A validated instance of `schema`.

    Raises:
        OutputSchemaValidationError: `result` does not conform to
            `schema`. Carries the underlying validation errors for
            logging/debugging (see the exception's docstring).
    """
    try:
        return schema.model_validate(result)
    except ValidationError as exc:
        raise OutputSchemaValidationError(schema, exc.errors()) from exc
