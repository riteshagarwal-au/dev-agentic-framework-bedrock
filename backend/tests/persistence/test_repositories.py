"""Unit tests for the DynamoDB repository layer (Task 5.6).

Covers RunState step-boundary idempotency, RunCounters atomic increment,
GateTicket create/read, and DeadLetterRecord create/list — per Task 5.6's
description.
"""

from datetime import UTC, datetime

from daf.models import (
    ApprovalContext,
    ArtifactKind,
    ArtifactLocationKind,
    ArtifactRef,
    GateTicket,
    GateTicketStatus,
    HitlGateType,
    RunCounters,
    RunStatus,
)
from daf.models.run import RunState
from daf.persistence.dead_letter_repository import DeadLetterRecordRepository
from daf.persistence.gate_ticket_repository import GateTicketRepository
from daf.persistence.run_counters_repository import RunCountersRepository
from daf.persistence.run_state_repository import RunStateRepository
from tests.persistence.fakes import FakeDynamoDBTable


def _run_state(run_id: str, step_index: int) -> RunState:
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


class TestRunStateRepository:
    def test_save_and_get_round_trip(self) -> None:
        repo = RunStateRepository(FakeDynamoDBTable(key_name="runId"))
        state = _run_state("run-1", step_index=0)

        assert repo.save(state) is True
        fetched = repo.get("run-1")

        assert fetched is not None
        assert fetched.run_id == "run-1"
        assert fetched.current_step_index == 0

    def test_stale_step_boundary_write_is_rejected(self) -> None:
        repo = RunStateRepository(FakeDynamoDBTable(key_name="runId"))
        repo.save(_run_state("run-1", step_index=2))

        applied = repo.save(_run_state("run-1", step_index=1))

        assert applied is False
        assert repo.get("run-1").current_step_index == 2

    def test_get_missing_run_returns_none(self) -> None:
        repo = RunStateRepository(FakeDynamoDBTable(key_name="runId"))
        assert repo.get("does-not-exist") is None


class TestRunCountersRepository:
    def test_increment_is_additive_and_atomic_per_call(self) -> None:
        repo = RunCountersRepository(FakeDynamoDBTable(key_name="runId"))
        repo.initialize("run-1")

        repo.increment("run-1", tokens_in=100, tokens_out=50, cost_usd=0.01)
        counters = repo.increment("run-1", tokens_in=10, cost_usd=0.02)

        assert counters.total_tokens_in == 110
        assert counters.total_tokens_out == 50
        assert round(float(counters.estimated_cost_usd), 4) == 0.03

    def test_negative_delta_rejected(self) -> None:
        repo = RunCountersRepository(FakeDynamoDBTable(key_name="runId"))
        try:
            repo.increment("run-1", tokens_in=-1)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError for negative delta")

    def test_get_missing_returns_none(self) -> None:
        repo = RunCountersRepository(FakeDynamoDBTable(key_name="runId"))
        assert repo.get("does-not-exist") is None


class TestGateTicketRepository:
    def _ticket(self) -> GateTicket:
        return GateTicket(
            ticketId="ticket-1",
            runId="run-1",
            gateType=HitlGateType.INFRA_APPLY,
            status=GateTicketStatus.PENDING,
            context=ApprovalContext(summary="apply plan X"),
            raisedAt=datetime.now(UTC),
        )

    def test_create_and_get(self) -> None:
        repo = GateTicketRepository(FakeDynamoDBTable(key_name="ticketId"))
        repo.create(self._ticket())

        fetched = repo.get("ticket-1")
        assert fetched is not None
        assert fetched.status == GateTicketStatus.PENDING

    def test_update_transitions_status(self) -> None:
        repo = GateTicketRepository(FakeDynamoDBTable(key_name="ticketId"))
        repo.create(self._ticket())

        approved = self._ticket().model_copy(update={"status": GateTicketStatus.APPROVED})
        repo.update(approved)

        assert repo.get("ticket-1").status == GateTicketStatus.APPROVED


class TestDeadLetterRecordRepository:
    def test_create_and_list_by_run(self) -> None:
        repo = DeadLetterRecordRepository(FakeDynamoDBTable(key_name="deadLetterId"))
        ref = ArtifactRef(
            artifactId="artifact-1",
            location="s3://bucket/key",
            locationKind=ArtifactLocationKind.S3_URI,
            kind=ArtifactKind.OTHER,
        )

        record = repo.create(
            run_id="run-1",
            task_envelope_ref=ref,
            error_detail="timeout after 3 retries",
            retry_count=3,
            trace_id="trace-1",
        )

        results = repo.list_by_run("run-1")
        assert len(results) == 1
        assert results[0].dead_letter_id == record.dead_letter_id
        assert results[0].retry_count == 3
