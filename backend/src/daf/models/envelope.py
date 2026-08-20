"""TaskEnvelope and SpokeResult — the SpokeAgent contract boundary.

design.md Component 5 "Common interface (all core agents implement this
contract)":

    STRUCTURE TaskEnvelope
      task: String
      inputs: Map<String, ArtifactRef>
      acceptanceCriteria: List<String>
      traceId: TraceId
    END STRUCTURE

    STRUCTURE SpokeResult
      output: ArtifactRef
      confidence: Float          // 0.0-1.0
      tokensUsed: TokenUsage
      status: SUCCESS | PARTIAL | FAILED
      notes: String
    END STRUCTURE

Requirement 2.2: "WHEN a core agent is invoked THEN the agent SHALL
receive only a TaskEnvelope (task, inputs as ArtifactRefs, acceptance
criteria, trace ID) and SHALL NOT receive full run history inline."
"""

from __future__ import annotations

from pydantic import ConfigDict, Field, field_validator

from daf.models.common import ArtifactRef, DafBaseModel, TokenUsage
from daf.models.enums import SpokeResultStatus
from daf.models.types import TraceId


class TaskEnvelope(DafBaseModel):
    """The bounded input a Supervisor passes to `SpokeAgent.execute`.

    The `ArtifactRef`-only rule (design.md Model 4 validation rules,
    source §6.4 point 1: "Large artifacts ... are never inlined into a
    TaskEnvelope — always passed by ArtifactRef") is enforced two ways:

    1. Structurally — `inputs` is typed `dict[str, ArtifactRef]`, so
       Pydantic rejects any value that isn't a valid `ArtifactRef` (e.g. a
       raw string of file content, or an arbitrary dict missing
       `ArtifactRef`'s required fields) at construction time.
    2. Explicitly — the `_inputs_must_be_artifact_refs` validator below
       re-asserts this in a way that is discoverable/test-friendly (it is
       the single call site a reader or test can point at to confirm the
       rule is enforced), rather than relying solely on the implicit
       behavior of the type annotation.
    """

    task: str = Field(min_length=1)
    inputs: dict[str, ArtifactRef] = Field(default_factory=dict, alias="inputs")
    acceptance_criteria: list[str] = Field(default_factory=list, alias="acceptanceCriteria")
    trace_id: TraceId = Field(alias="traceId")

    model_config = ConfigDict(extra="forbid", validate_assignment=True, populate_by_name=True)

    @field_validator("inputs")
    @classmethod
    def _inputs_must_be_artifact_refs(cls, value: dict[str, ArtifactRef]) -> dict[str, ArtifactRef]:
        """Explicit enforcement point for the ArtifactRef-only rule.

        By the time this runs, Pydantic has already coerced/validated each
        value into an `ArtifactRef` (or raised). This validator exists so
        the rule has a single, discoverable, test-targetable location —
        see Task 6.3's `TaskEnvelope.inputs` enforcement tests — rather
        than relying purely on the type annotation being read correctly.
        """
        for key, artifact in value.items():
            if not isinstance(artifact, ArtifactRef):
                raise ValueError(
                    f"TaskEnvelope.inputs[{key!r}] must be an ArtifactRef, "
                    f"never inlined artifact content (got {type(artifact).__name__})"
                )
        return value


class SpokeResult(DafBaseModel):
    """The structured result every `SpokeAgent.execute` call returns."""

    output: ArtifactRef
    confidence: float = Field(ge=0.0, le=1.0)
    tokens_used: TokenUsage = Field(alias="tokensUsed")
    status: SpokeResultStatus
    notes: str = ""

    model_config = ConfigDict(extra="forbid", validate_assignment=True, populate_by_name=True)
