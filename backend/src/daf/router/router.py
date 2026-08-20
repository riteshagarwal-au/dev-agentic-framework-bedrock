"""`resolve_model` (Task 7.1) and `record_outcome`/escalation logging (Task 7.2).

Design ref: design.md "Algorithm 1: Deterministic Router + Agentic Escalation".
"""

from __future__ import annotations

import logging
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from daf.models.enums import ModelTier, SpokeResultStatus, TaskType
from daf.models.types import RunId, TaskId
from daf.router.exceptions import RunHalt
from daf.router.policy import CONFIDENCE_THRESHOLD, MAX_SONNET_RETRIES, TASK_MODEL_POLICY

logger = logging.getLogger(__name__)


class AttemptState(BaseModel):
    """Per-task retry state `resolve_model` reads (design.md `AttemptState`).

    `attempt_number` starts at 1 and increments only on a retry of the
    *same* task (design.md Algorithm 1 preconditions).
    """

    run_id: RunId
    task_id: TaskId
    attempt_number: int = Field(ge=1, default=1)
    last_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    last_status: SpokeResultStatus | None = None

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class OpusGateProtocol(Protocol):
    """The subset of the Cost/Budget Counter Hook's `checkOpusGate`
    (Task 8.3) `resolve_model` depends on. Typed as a `Protocol` so tests
    can pass a stub without constructing the full hook.
    """

    def check_opus_gate(self, run_id: RunId) -> bool:
        """Return True if another Opus invocation is within budget for `run_id`."""
        ...


def resolve_model(
    task_type: TaskType,
    attempt_state: AttemptState,
    opus_gate: OpusGateProtocol,
) -> ModelTier:
    """Resolve the model tier for a task attempt, escalating on retry.

    Raises:
        RunHalt: escalation ladder exhausted, or the Opus gate denies
            escalation (design.md Algorithm 1 postconditions — never
            silently returns a tier the caller didn't ask to escalate to).
    """
    if task_type not in TASK_MODEL_POLICY:
        raise KeyError(f"TASK_MODEL_POLICY has no entry for TaskType {task_type!r} (must be exhaustive)")
    default_tier = TASK_MODEL_POLICY[task_type]

    if attempt_state.attempt_number == 1:
        return default_tier

    if not (
        (attempt_state.last_confidence is not None and attempt_state.last_confidence < CONFIDENCE_THRESHOLD)
        or attempt_state.last_status == SpokeResultStatus.FAILED
    ):
        raise ValueError(
            "resolve_model called for a retry (attempt_number > 1) but neither "
            "last_confidence < CONFIDENCE_THRESHOLD nor last_status == FAILED holds"
        )

    if default_tier == ModelTier.HAIKU:
        return _log_escalation(attempt_state.task_id, default_tier, ModelTier.SONNET, "haiku retry ladder")

    if default_tier == ModelTier.SONNET:
        if attempt_state.attempt_number > MAX_SONNET_RETRIES:
            if opus_gate.check_opus_gate(attempt_state.run_id):
                return _log_escalation(
                    attempt_state.task_id, default_tier, ModelTier.OPUS, "sonnet retries exhausted"
                )
            raise RunHalt(
                f"Opus escalation blocked for task {attempt_state.task_id!r}: opus budget exhausted for this run"
            )
        return ModelTier.SONNET

    # default_tier == OPUS and still failing: no further ladder rung.
    raise RunHalt(f"Opus tier exhausted for task {attempt_state.task_id!r}")


def _log_escalation(task_id: TaskId, from_tier: ModelTier, to_tier: ModelTier, reason: str) -> ModelTier:
    logger.info(
        "model_tier_escalated",
        extra={"taskId": task_id, "fromTier": from_tier.value, "toTier": to_tier.value, "reason": reason},
    )
    return to_tier


def record_outcome(
    attempt_state: AttemptState,
    tier: ModelTier,
    confidence: float,
    succeeded: bool,
) -> AttemptState:
    """Update `attempt_state` after an invocation, advancing
    `attempt_number` on failure/low-confidence so the next `resolve_model`
    call escalates correctly (design.md Algorithm 4:
    `Router.recordOutcome(taskId, tier, confidence, succeeded)`).

    Returns a new `AttemptState` — this function does not mutate its input
    (repositories/callers are responsible for persisting the result).
    """
    if succeeded:
        return attempt_state.model_copy(
            update={
                "last_confidence": confidence,
                "last_status": SpokeResultStatus.SUCCESS,
            }
        )
    return attempt_state.model_copy(
        update={
            "attempt_number": attempt_state.attempt_number + 1,
            "last_confidence": confidence,
            "last_status": SpokeResultStatus.FAILED,
        }
    )
