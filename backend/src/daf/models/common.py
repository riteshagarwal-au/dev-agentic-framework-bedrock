"""Small shared structures referenced by the four main data models.

design.md defines `ArtifactRef` under "Model 4: TaskEnvelope / ArtifactRef"
but it is also referenced by `RunConfig` (via `AzureSourceRef`, informally)
and by `SpokeResult.output`. Keeping these small, widely-referenced structs
in one module avoids circular imports between `envelope.py`, `run.py`, and
`gate.py`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from daf.models.enums import ArtifactKind, ArtifactLocationKind


class DafBaseModel(BaseModel):
    """Shared Pydantic base for every DAF model.

    `extra="forbid"` is deliberate: these models are the contract boundary
    a spoke agent receives (Requirement 2.2) and the boundary the hook
    pipeline validates against (design.md Algorithm 4, `validateOutputSchema`).
    Silently accepting unknown fields would undermine that contract, so
    unexpected fields are a validation error rather than being dropped.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ArtifactRef(DafBaseModel):
    """A pointer to an artifact's storage location — never the artifact's
    content itself.

    design.md Model 4:
        STRUCTURE ArtifactRef
          artifactId: String
          location: S3_URI | DYNAMODB_KEY
          kind: SOURCE_TREE | BLUEPRINT | TF_PLAN | INVENTORY | OTHER
        END STRUCTURE

    This is the type every `TaskEnvelope.inputs` value and `SpokeResult.output`
    MUST be — see `TaskEnvelope` for the enforcement point of the
    "ArtifactRef-only, never inlined content" rule (Requirement 2.2,
    design.md Model 4 validation rules, source §6.4 point 1).
    """

    artifact_id: str = Field(min_length=1, alias="artifactId")
    location: str = Field(
        min_length=1,
        description=(
            "The location string itself (an S3 URI or a DynamoDB key), "
            "interpreted according to `location_kind`."
        ),
    )
    location_kind: ArtifactLocationKind = Field(alias="locationKind")
    kind: ArtifactKind

    model_config = ConfigDict(extra="forbid", validate_assignment=True, populate_by_name=True)


class TokenUsage(DafBaseModel):
    """`SpokeResult.tokensUsed` (design.md Component 5 common interface,
    "define as a small struct: tokensIn, tokensOut").
    """

    tokens_in: int = Field(ge=0, alias="tokensIn")
    tokens_out: int = Field(ge=0, alias="tokensOut")

    model_config = ConfigDict(extra="forbid", validate_assignment=True, populate_by_name=True)


class AzureSourceRef(DafBaseModel):
    """Reference to the Azure source environment being migrated
    (design.md Model 1 `RunConfig.sourceEnv: AzureSourceRef`).

    design.md does not expand this structure's fields beyond naming it;
    per source design §1/§14 the synthetic app source is either a real
    non-production Azure subscription or a simulated discovery response
    (open item, not yet resolved). This model captures the minimal
    identifying fields needed either way without prescribing which.
    """

    subscription_id: str = Field(min_length=1, alias="subscriptionId")
    resource_group: str = Field(min_length=1, alias="resourceGroup")
    resource_name: str = Field(min_length=1, alias="resourceName")

    model_config = ConfigDict(extra="forbid", validate_assignment=True, populate_by_name=True)


class ApprovalContext(DafBaseModel):
    """Context shown to a human approver for a HITL gate decision
    (design.md Model 3 `GateTicket.context: ApprovalContext`).

    `artifactRefs` carries pointers (never inlined artifact content, same
    rule as `TaskEnvelope.inputs`); `summary` is the human-readable text
    surfaced in the portal (Requirement 12.3).
    """

    summary: str = Field(min_length=1)
    artifact_refs: list[ArtifactRef] = Field(default_factory=list, alias="artifactRefs")
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", validate_assignment=True, populate_by_name=True)


class TaskNode(DafBaseModel):
    """A single node in a run's task graph (design.md Model 1
    `RunState.taskGraph: List<TaskNode>`).

    design.md does not expand `TaskNode`'s fields; this is the minimal
    shape needed to represent "one step of the task graph, its assigned
    agent, and whether it is complete" for resumability (Requirement 8.1,
    8.5, Property 8).
    """

    task_id: str = Field(min_length=1, alias="taskId")
    task_type: str = Field(min_length=1, alias="taskType")
    agent_id: str = Field(min_length=1, alias="agentId")
    completed: bool = False

    model_config = ConfigDict(extra="forbid", validate_assignment=True, populate_by_name=True)
