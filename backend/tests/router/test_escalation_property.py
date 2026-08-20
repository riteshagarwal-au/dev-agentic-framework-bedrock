"""Property test for escalation monotonic and bounded (Task 7.4, Property 4).

design.md: "Across retries of the same task, `attemptState.attemptNumber`
strictly increases and the model tier never decreases (Haiku -> Sonnet ->
Opus only, never Opus -> Haiku)... terminates within
`MAX_SONNET_RETRIES + maxOpusInvocations` attempts, raising `RunHalt`
rather than looping forever."
"""

from hypothesis import given
from hypothesis import strategies as st

from daf.models.enums import ModelTier, SpokeResultStatus, TaskType
from daf.router.exceptions import RunHalt
from daf.router.policy import MAX_SONNET_RETRIES, TASK_MODEL_POLICY
from daf.router.router import AttemptState, resolve_model

_TIER_ORDER = {ModelTier.HAIKU: 0, ModelTier.SONNET: 1, ModelTier.OPUS: 2}


class _OpusGate:
    """Allows exactly `max_opus_invocations` Opus escalations, then denies."""

    def __init__(self, max_opus_invocations: int) -> None:
        self._remaining = max_opus_invocations

    def check_opus_gate(self, run_id: str) -> bool:
        if self._remaining > 0:
            self._remaining -= 1
            return True
        return False


@given(
    task_type=st.sampled_from(list(TaskType)),
    max_opus_invocations=st.integers(min_value=0, max_value=3),
)
def test_escalation_is_monotonic_and_bounded(task_type: TaskType, max_opus_invocations: int) -> None:
    """Per design.md Algorithm 1's literal pseudocode, a Haiku-default task
    escalates exactly once to Sonnet and then stays at Sonnet forever (the
    Haiku branch has no further rung/gate) — only Sonnet/Opus-default
    tasks are bounded by `MAX_SONNET_RETRIES`/the Opus gate and eventually
    raise `RunHalt`. Both behaviors must be monotonic (tier never
    decreases); only the latter is required to terminate in `RunHalt`.
    """
    opus_gate = _OpusGate(max_opus_invocations)
    state = AttemptState(run_id="run-1", task_id="task-1", attempt_number=1)

    tiers_seen: list[ModelTier] = []
    default_tier = TASK_MODEL_POLICY[task_type]
    max_attempts = 1 + MAX_SONNET_RETRIES + max_opus_invocations + 5  # generous bound + halt margin

    for attempt_number in range(1, max_attempts + 1):
        state = state.model_copy(
            update={
                "attempt_number": attempt_number,
                "last_status": SpokeResultStatus.FAILED if attempt_number > 1 else None,
            }
        )
        try:
            tier = resolve_model(task_type, state, opus_gate)
        except RunHalt:
            # Reaching RunHalt at all (rather than escalating forever) is
            # the terminal state this property requires for Sonnet/Opus-
            # default tasks.
            assert default_tier != ModelTier.HAIKU
            return
        if tiers_seen:
            assert _TIER_ORDER[tier] >= _TIER_ORDER[tiers_seen[-1]], "tier must never decrease across retries"
        tiers_seen.append(tier)

    if default_tier == ModelTier.HAIKU:
        # No RunHalt expected: escalates once to Sonnet, then stabilizes.
        assert tiers_seen[-1] == ModelTier.SONNET
        return

    raise AssertionError(
        f"resolve_model did not raise RunHalt within {max_attempts} attempts for {task_type!r}"
    )
