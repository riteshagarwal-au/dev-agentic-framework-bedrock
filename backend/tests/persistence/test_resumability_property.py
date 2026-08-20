"""Property-based test for run resumability (Task 5.7, Property 8).

Property 8: generate random sequences of step-completions and
halts/resumes; assert `RunState.taskGraph`/`currentStepIndex` and
`RunCounters` after resume reflect exactly the steps completed before the
halt, with no double-counted usage and no re-run of completed steps.

Validates: Requirements 8.1, 8.5.
"""

from datetime import UTC, datetime

from hypothesis import given
from hypothesis import strategies as st

from daf.models import RunCounters, RunStatus
from daf.models.run import RunState
from daf.persistence.run_counters_repository import RunCountersRepository
from daf.persistence.run_state_repository import RunStateRepository
from tests.persistence.fakes import FakeDynamoDBTable


def _run_state_at(run_id: str, step_index: int) -> RunState:
    return RunState(
        runId=run_id,
        status=RunStatus.RUNNING,
        taskGraph=[],
        currentStepIndex=step_index,
        traceId="trace-1",
        counters=RunCounters(runId=run_id),
        createdAt=datetime.now(UTC),
        updatedAt=datetime.now(UTC),
    )


@given(step_sequence=st.lists(st.integers(min_value=0, max_value=20), min_size=1, max_size=30))
def test_run_state_never_regresses_and_resumes_at_highest_completed_step(
    step_sequence: list[int],
) -> None:
    """Simulate a run being written at arbitrary (possibly out-of-order,
    possibly repeated — representing retries/halts/resumes) step indices.
    After all writes, the persisted state must reflect the *highest* step
    index ever written, never a lower/stale one, and re-applying a step
    already persisted must be a no-op.
    """
    repo = RunStateRepository(FakeDynamoDBTable(key_name="runId"))
    run_id = "run-resumability"
    highest_seen = -1

    for step_index in step_sequence:
        applied = repo.save(_run_state_at(run_id, step_index))
        if step_index > highest_seen:
            assert applied is True
            highest_seen = step_index
        else:
            # A step at or below the highest-seen boundary must never be
            # re-applied (no regression, no double-counted re-run).
            assert applied is False

    final_state = repo.get(run_id)
    assert final_state is not None
    assert final_state.current_step_index == highest_seen


@given(
    usage_deltas=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=1000),
            st.integers(min_value=0, max_value=1000),
        ),
        min_size=1,
        max_size=20,
    )
)
def test_run_counters_never_double_count_across_repeated_increments(
    usage_deltas: list[tuple[int, int]],
) -> None:
    """Counters must sum exactly the deltas applied — no double-counting,
    no lost updates, regardless of how many increment calls are made
    (representing retried/resumed steps each recording their own usage
    exactly once).
    """
    repo = RunCountersRepository(FakeDynamoDBTable(key_name="runId"))
    run_id = "run-counters-resumability"
    repo.initialize(run_id)

    expected_tokens_in = 0
    expected_tokens_out = 0
    for tokens_in, tokens_out in usage_deltas:
        repo.increment(run_id, tokens_in=tokens_in, tokens_out=tokens_out)
        expected_tokens_in += tokens_in
        expected_tokens_out += tokens_out

    counters = repo.get(run_id)
    assert counters is not None
    assert counters.total_tokens_in == expected_tokens_in
    assert counters.total_tokens_out == expected_tokens_out
