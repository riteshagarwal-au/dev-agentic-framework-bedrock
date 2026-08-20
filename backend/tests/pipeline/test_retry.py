"""Unit tests for backoff retry and dead-letter persistence (Task 10.6)."""

import pytest

from daf.models.common import ArtifactRef
from daf.models.enums import ArtifactKind, ArtifactLocationKind
from daf.persistence.dead_letter_repository import DeadLetterRecordRepository
from daf.pipeline.retry import retry_with_backoff
from tests.persistence.fakes import FakeDynamoDBTable


class TransientError(Exception):
    pass


class PermanentError(Exception):
    pass


def _ref() -> ArtifactRef:
    return ArtifactRef(
        artifactId="a1", location="s3://bucket/key", locationKind=ArtifactLocationKind.S3_URI, kind=ArtifactKind.OTHER
    )


def test_succeeds_after_transient_failures_without_dead_lettering() -> None:
    dead_letters = DeadLetterRecordRepository(FakeDynamoDBTable(key_name="deadLetterId"))
    attempts = {"count": 0}
    sleeps: list[float] = []

    def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise TransientError("temporary")
        return "ok"

    result = retry_with_backoff(
        flaky, max_attempts=5, base_delay_seconds=1.0, is_transient=lambda exc: isinstance(exc, TransientError),
        dead_letter_repo=dead_letters, run_id="run-1", task_envelope_ref=_ref(), trace_id="trace-1",
        sleep=sleeps.append,
    )

    assert result == "ok"
    assert attempts["count"] == 3
    assert sleeps == [1.0, 2.0]
    assert dead_letters.list_by_run("run-1") == []


def test_exhausted_retries_persists_dead_letter_and_reraises() -> None:
    dead_letters = DeadLetterRecordRepository(FakeDynamoDBTable(key_name="deadLetterId"))

    def always_fails() -> str:
        raise TransientError("still failing")

    with pytest.raises(TransientError):
        retry_with_backoff(
            always_fails, max_attempts=3, base_delay_seconds=0.01,
            is_transient=lambda exc: isinstance(exc, TransientError),
            dead_letter_repo=dead_letters, run_id="run-1", task_envelope_ref=_ref(), trace_id="trace-1",
            sleep=lambda _: None,
        )

    records = dead_letters.list_by_run("run-1")
    assert len(records) == 1
    assert records[0].retry_count == 3


def test_non_transient_error_is_not_retried() -> None:
    dead_letters = DeadLetterRecordRepository(FakeDynamoDBTable(key_name="deadLetterId"))
    attempts = {"count": 0}

    def fails_permanently() -> str:
        attempts["count"] += 1
        raise PermanentError("bad input")

    with pytest.raises(PermanentError):
        retry_with_backoff(
            fails_permanently, max_attempts=5, base_delay_seconds=0.01,
            is_transient=lambda exc: isinstance(exc, TransientError),
            dead_letter_repo=dead_letters, run_id="run-1", task_envelope_ref=_ref(), trace_id="trace-1",
            sleep=lambda _: None,
        )

    assert attempts["count"] == 1
    assert len(dead_letters.list_by_run("run-1")) == 1
