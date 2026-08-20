"""Shared enums for DAF Phase 1 data models.

Mirrors the `ENUM`/inline-union types from design.md's "Data Models"
section exactly, including values design.md defines for forward
compatibility but that Phase 1 logic does not yet populate (e.g.
`GateTicketStatus.EXPIRED`, `TargetPlatform.EKS` / `TargetPlatform.AZURE`).
"""

from enum import StrEnum


class ModelTier(StrEnum):
    """Bedrock model tier used by the Deterministic Router (design.md
    Algorithm 1). Ordered Haiku < Sonnet < Opus to support the monotonic
    escalation invariant (Requirement 3.7); see `models.router` policy
    helpers (Task 7.x) for the ordering logic itself — this enum only
    defines the values.
    """

    HAIKU = "HAIKU"
    SONNET = "SONNET"
    OPUS = "OPUS"


class RunStatus(StrEnum):
    """The six run statuses `Supervisor.getRunStatus` must return one of
    (Requirement 1.4, design.md Model 1 `RunState.status`).
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    HALTED = "HALTED"
    AWAITING_HITL = "AWAITING_HITL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TargetPlatform(StrEnum):
    """Redeploy target platform for a run (design.md Model 1 `RunConfig`).

    All three values are defined for forward compatibility with source
    design §13 (EKS / Azure redeploy is Phase 2+), but Phase 1 restricts
    `RunConfig.targetPlatform` to `ECS_FARGATE` only via a model validator
    (see `models.run.RunConfig`) rather than narrowing this enum itself,
    per design.md's explicit Phase 1 note and requirements.md's "Out of
    Scope for Phase 1" section (EKS and Azure redeploy targets).
    """

    ECS_FARGATE = "ECS_FARGATE"
    EKS = "EKS"
    AZURE = "AZURE"


class HitlGateType(StrEnum):
    """The 7 HITL gate types (design.md Model 3, Requirement 5.1).

    Order below matches the numbering used in design.md's inline comments
    (gate 1..7), not alphabetical order, to keep this enum easy to cross
    reference against the design document.
    """

    INFRA_APPLY = "INFRA_APPLY"  # gate 1
    PR_MERGE = "PR_MERGE"  # gate 2
    DESTRUCTIVE_ACTION = "DESTRUCTIVE_ACTION"  # gate 3
    WORKER_SPINUP = "WORKER_SPINUP"  # gate 4
    KB_WRITE = "KB_WRITE"  # gate 5
    PLAN_FINALIZE = "PLAN_FINALIZE"  # gate 6
    CLOUD_DEPLOY = "CLOUD_DEPLOY"  # gate 7


class GateTicketStatus(StrEnum):
    """`GateTicket.status` (design.md Model 3). `EXPIRED` exists in the
    model for forward compatibility only — no Phase 1 logic populates it
    (design.md Model 3 validation rules; requirements.md Requirement 5.8
    defers approval-expiry/timeout to Phase 2).
    """

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ArtifactLocationKind(StrEnum):
    """Storage backend an `ArtifactRef.location` points into (design.md
    Model 4 `ArtifactRef`). This describes *where* the location string
    should be interpreted, not the location value itself.
    """

    S3_URI = "S3_URI"
    DYNAMODB_KEY = "DYNAMODB_KEY"


class ArtifactKind(StrEnum):
    """The kind of artifact an `ArtifactRef` points to (design.md Model 4)."""

    SOURCE_TREE = "SOURCE_TREE"
    BLUEPRINT = "BLUEPRINT"
    TF_PLAN = "TF_PLAN"
    INVENTORY = "INVENTORY"
    OTHER = "OTHER"


class SpokeResultStatus(StrEnum):
    """`SpokeResult.status` (design.md Component 5 common interface)."""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class TaskType(StrEnum):
    """Task categories the Deterministic Router's `TASK_MODEL_POLICY`
    (design.md Algorithm 1, source §5.2) maps to a default `ModelTier`.

    design.md's Component 5 agent table gives per-agent defaults, some
    agents split by task category (e.g. Discovery: "Sonnet 5 (reason) /
    Haiku (collect)"; DevOps: "Haiku (exec), Sonnet on escalation") — this
    enum's values follow that split so `TASK_MODEL_POLICY` (Task 7.1) can
    be exhaustive over one entry per agent-task-category rather than one
    entry per agent.
    """

    DISCOVERY_COLLECT = "DISCOVERY_COLLECT"
    DISCOVERY_REASON = "DISCOVERY_REASON"
    DEVOPS_EXEC = "DEVOPS_EXEC"
    SECURITY_REVIEW = "SECURITY_REVIEW"
    MODERNIZATION_PLAN = "MODERNIZATION_PLAN"
    PORTFOLIO_ASSESSMENT = "PORTFOLIO_ASSESSMENT"
    PR_REVIEW = "PR_REVIEW"
