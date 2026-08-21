"""RunConfig and RunState (design.md "Model 1: RunConfig / RunState")."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import ConfigDict, Field, field_validator

from daf.models.budget import BudgetCeiling, RunCounters
from daf.models.common import ArtifactRef, AzureSourceRef, DafBaseModel, TaskNode
from daf.models.enums import RunStatus, TargetPlatform
from daf.models.types import RunId, TraceId

_TARGET_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class RunConfig(DafBaseModel):
    """Immutable configuration a run is started with (design.md Model 1).

    design.md defines `targetPlatform` as a 3-value enum
    (`ECS_FARGATE | EKS | AZURE`) but immediately notes "Phase 1 =
    ECS_FARGATE only" and requirements.md's "Out of Scope for Phase 1"
    section lists "EKS and Azure redeploy targets" explicitly. The enum
    keeps all 3 values for forward compatibility (Phase 2+), and the
    `_restrict_to_ecs_fargate_in_phase_1` validator below is what actually
    enforces the Phase 1 restriction by raising on anything else, rather
    than silently accepting a value Phase 1 logic can't act on.
    """

    run_id: RunId = Field(alias="runId")
    target_app: str = Field(min_length=1, alias="targetApp")
    source_env: AzureSourceRef = Field(alias="sourceEnv")
    target_platform: TargetPlatform = Field(alias="targetPlatform")
    budget_ceiling: BudgetCeiling = Field(alias="budgetCeiling")
    # "org/repo" for the target/synthetic app's own GitHub repo (distinct from the DAF repo
    # itself) — DevOps/PR-Reviewer agents open PRs and read diffs here via the GitHub MCP
    # connector, e.g. "riteshagarwal-au/appmigration-daf".
    target_repo: str = Field(alias="targetRepo")

    model_config = ConfigDict(extra="forbid", validate_assignment=True, populate_by_name=True)

    @field_validator("target_repo")
    @classmethod
    def _target_repo_must_be_org_slash_repo(cls, value: str) -> str:
        if not _TARGET_REPO_PATTERN.match(value):
            raise ValueError(f"targetRepo={value!r} must be in \"org/repo\" form")
        return value

    @field_validator("target_platform")
    @classmethod
    def _restrict_to_ecs_fargate_in_phase_1(cls, value: TargetPlatform) -> TargetPlatform:
        if value is not TargetPlatform.ECS_FARGATE:
            raise ValueError(
                f"targetPlatform={value.value!r} is not supported in Phase 1; "
                "only ECS_FARGATE is supported (EKS/AZURE are Phase 2+, "
                "see design.md Model 1 and requirements.md 'Out of Scope for Phase 1')"
            )
        return value


class RunState(DafBaseModel):
    """Durable, persisted run state (design.md Model 1).

    `taskGraph` and `counters` are what make a run resumable (Requirement
    8.1, 8.5, Property 8) — see the `RunStateRepository` (Task 5.2) for the
    persistence/idempotent-write behavior; this model only defines the
    shape.
    """

    run_id: RunId = Field(alias="runId")
    status: RunStatus
    task_graph: list[TaskNode] = Field(default_factory=list, alias="taskGraph")
    current_step_index: int = Field(ge=0, default=0, alias="currentStepIndex")
    trace_id: TraceId = Field(alias="traceId")
    counters: RunCounters
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    # Keyed by TaskType value — lets the Supervisor pass a completed step's real
    # ArtifactRef output into a later step's TaskEnvelope.inputs (e.g. Discovery's
    # inventory feeding Modernization) instead of every step always getting inputs={}.
    task_outputs: dict[str, ArtifactRef] = Field(default_factory=dict, alias="taskOutputs")

    model_config = ConfigDict(extra="forbid", validate_assignment=True, populate_by_name=True)
