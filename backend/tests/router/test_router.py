"""Unit tests for the Deterministic Router (Task 7.3).

Covers TASK_MODEL_POLICY exhaustiveness and the escalation-ladder edge
cases in `resolve_model`.
"""

import pytest

from daf.models.enums import ModelTier, SpokeResultStatus, TaskType
from daf.router.exceptions import RunHalt
from daf.router.policy import MAX_SONNET_RETRIES, TASK_MODEL_POLICY
from daf.router.router import AttemptState, resolve_model


class _OpusGate:
    def __init__(self, allowed: bool) -> None:
        self._allowed = allowed

    def check_opus_gate(self, run_id: str) -> bool:
        return self._allowed


def test_policy_table_is_exhaustive_over_every_task_type() -> None:
    assert set(TASK_MODEL_POLICY.keys()) == set(TaskType)


def test_first_attempt_returns_default_tier() -> None:
    state = AttemptState(run_id="run-1", task_id="task-1", attempt_number=1)
    tier = resolve_model(TaskType.DEVOPS_EXEC, state, _OpusGate(allowed=True))
    assert tier == TASK_MODEL_POLICY[TaskType.DEVOPS_EXEC]


def test_haiku_default_escalates_to_sonnet_on_retry() -> None:
    state = AttemptState(
        run_id="run-1", task_id="task-1", attempt_number=2, last_status=SpokeResultStatus.FAILED
    )
    tier = resolve_model(TaskType.DEVOPS_EXEC, state, _OpusGate(allowed=True))
    assert tier == ModelTier.SONNET


def test_sonnet_default_retries_at_sonnet_before_max_retries() -> None:
    state = AttemptState(
        run_id="run-1", task_id="task-1", attempt_number=2, last_status=SpokeResultStatus.FAILED
    )
    tier = resolve_model(TaskType.SECURITY_REVIEW, state, _OpusGate(allowed=True))
    assert tier == ModelTier.SONNET


def test_sonnet_escalates_to_opus_after_max_retries_when_gate_allows() -> None:
    state = AttemptState(
        run_id="run-1",
        task_id="task-1",
        attempt_number=MAX_SONNET_RETRIES + 2,
        last_status=SpokeResultStatus.FAILED,
    )
    tier = resolve_model(TaskType.SECURITY_REVIEW, state, _OpusGate(allowed=True))
    assert tier == ModelTier.OPUS


def test_sonnet_escalation_halts_when_opus_gate_denies() -> None:
    state = AttemptState(
        run_id="run-1",
        task_id="task-1",
        attempt_number=MAX_SONNET_RETRIES + 2,
        last_status=SpokeResultStatus.FAILED,
    )
    with pytest.raises(RunHalt):
        resolve_model(TaskType.SECURITY_REVIEW, state, _OpusGate(allowed=False))


def test_unknown_task_type_raises_key_error() -> None:
    state = AttemptState(run_id="run-1", task_id="task-1", attempt_number=1)
    with pytest.raises(KeyError):
        resolve_model("NOT_A_REAL_TASK_TYPE", state, _OpusGate(allowed=True))  # type: ignore[arg-type]


def test_retry_without_low_confidence_or_failed_status_is_rejected() -> None:
    state = AttemptState(
        run_id="run-1",
        task_id="task-1",
        attempt_number=2,
        last_confidence=0.99,
        last_status=SpokeResultStatus.SUCCESS,
    )
    with pytest.raises(ValueError):
        resolve_model(TaskType.DEVOPS_EXEC, state, _OpusGate(allowed=True))
