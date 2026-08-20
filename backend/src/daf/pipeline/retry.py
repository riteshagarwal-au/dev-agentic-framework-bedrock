"""Dead-simple exponential-backoff retry helper with dead-letter
persistence on exhaustion (Task 10.4).

Design ref: design.md Algorithm 4 postconditions (transient-error retry);
Requirement 8.3 (dead-letter persistence on exhausted retries).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from daf.models.common import ArtifactRef
from daf.persistence.dead_letter_repository import DeadLetterRecordRepository

T = TypeVar("T")


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    max_attempts: int,
    base_delay_seconds: float,
    is_transient: Callable[[Exception], bool],
    dead_letter_repo: DeadLetterRecordRepository,
    run_id: str,
    task_envelope_ref: ArtifactRef,
    trace_id: str,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call `fn()`, retrying transient failures with exponential backoff
    (`base_delay_seconds * 2**attempt`). On exhausting `max_attempts`,
    persists a `DeadLetterRecord` and re-raises the last exception —
    "SHALL NOT silently drop the failure" (Requirement 8.3).
    """
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - re-raised/persisted below, never swallowed
            last_exc = exc
            if not is_transient(exc) or attempt == max_attempts - 1:
                break
            sleep(base_delay_seconds * (2**attempt))

    assert last_exc is not None
    dead_letter_repo.create(
        run_id=run_id,
        task_envelope_ref=task_envelope_ref,
        error_detail=str(last_exc),
        retry_count=max_attempts,
        trace_id=trace_id,
    )
    raise last_exc
