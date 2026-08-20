"""Shared Pydantic data models and enums for DAF Phase 1.

These types are the data-model portion of design.md's "Data Models" section
and Component 5's "Common interface" (SpokeAgent contract). They are the
concrete, validated Python representations of the structures the design
document expresses as pseudocode `STRUCTURE`/`ENUM` blocks.

See:
- .kiro/specs/daf-phase1-foundations/design.md#data-models
- .kiro/specs/daf-phase1-foundations/requirements.md (Requirements 2.2, 4.4)
"""

from daf.models.budget import BudgetCeiling, RunCounters
from daf.models.common import (
    ApprovalContext,
    ArtifactRef,
    AzureSourceRef,
    DafBaseModel,
    TaskNode,
    TokenUsage,
)
from daf.models.enums import (
    ArtifactKind,
    ArtifactLocationKind,
    GateTicketStatus,
    HitlGateType,
    ModelTier,
    RunStatus,
    SpokeResultStatus,
    TargetPlatform,
    TaskType,
)
from daf.models.deadletter import DeadLetterRecord
from daf.models.envelope import SpokeResult, TaskEnvelope
from daf.models.gate import GateTicket
from daf.models.run import RunConfig, RunState
from daf.models.types import (
    AgentId,
    GateTicketId,
    RunId,
    TaskId,
    TraceId,
    UserId,
)

__all__ = [
    # enums
    "ArtifactKind",
    "ArtifactLocationKind",
    "GateTicketStatus",
    "HitlGateType",
    "ModelTier",
    "RunStatus",
    "SpokeResultStatus",
    "TargetPlatform",
    "TaskType",
    # type aliases
    "AgentId",
    "GateTicketId",
    "RunId",
    "TaskId",
    "TraceId",
    "UserId",
    # base
    "DafBaseModel",
    # common / shared structs
    "ApprovalContext",
    "ArtifactRef",
    "AzureSourceRef",
    "TaskNode",
    "TokenUsage",
    # envelope / spoke contract
    "SpokeResult",
    "TaskEnvelope",
    # run + budget
    "BudgetCeiling",
    "RunConfig",
    "RunCounters",
    "RunState",
    # HITL
    "GateTicket",
    # dead-letter
    "DeadLetterRecord",
]
