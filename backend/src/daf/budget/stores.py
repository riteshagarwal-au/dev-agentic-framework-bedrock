"""Bounded-window state trackers the Cost/Budget Counter Hook depends on.

Each store is defined as a `Protocol` (so a future DynamoDB-backed
implementation can replace the in-memory reference implementation without
changing `CostBudgetHook`), plus an in-memory implementation suitable for
a single Lambda invocation's lifetime / tests.

design.md's Loop Invariants for `detectRepeatedNoProgress`/
`detectConsecutiveFailures`: both must be O(1)/bounded-window, never an
unbounded scan over full run history — enforced here by `deque(maxlen=...)`
for the step history and a plain bounded counter (reset on non-FAILED) for
consecutive failures.
"""

from __future__ import annotations

from collections import deque
from typing import Protocol

from daf.budget.policy import NO_PROGRESS_LOOKBACK
from daf.models.enums import SpokeResultStatus


class KillSwitchStore(Protocol):
    def is_active(self, run_id: str) -> bool: ...

    def set_active(self, run_id: str, active: bool) -> None: ...


class IdempotencyStore(Protocol):
    def already_recorded(self, run_id: str, agent_id: str, idempotency_key: str) -> bool: ...

    def mark_recorded(self, run_id: str, agent_id: str, idempotency_key: str) -> None: ...


class StepHistoryStore(Protocol):
    def record_step(self, run_id: str, agent_id: str, tool_call_signature: str, progressed: bool) -> None: ...

    def detect_repeated_no_progress(self, run_id: str) -> bool: ...


class FailureCounterStore(Protocol):
    def record_result(self, run_id: str, agent_id: str, status: SpokeResultStatus) -> None: ...

    def detect_consecutive_failures(self, run_id: str, agent_id: str) -> bool: ...


class InMemoryKillSwitchStore:
    def __init__(self) -> None:
        self._active: dict[str, bool] = {}

    def is_active(self, run_id: str) -> bool:
        return self._active.get(run_id, False)

    def set_active(self, run_id: str, active: bool) -> None:
        self._active[run_id] = active


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._seen: set[tuple[str, str, str]] = set()

    def already_recorded(self, run_id: str, agent_id: str, idempotency_key: str) -> bool:
        return (run_id, agent_id, idempotency_key) in self._seen

    def mark_recorded(self, run_id: str, agent_id: str, idempotency_key: str) -> None:
        self._seen.add((run_id, agent_id, idempotency_key))


class InMemoryStepHistoryStore:
    """Tracks the last `NO_PROGRESS_LOOKBACK` `(agentId, toolCallSignature)`
    pairs per run, plus whether each of those steps advanced the run's
    task-graph progress pointer.
    """

    def __init__(self, lookback: int = NO_PROGRESS_LOOKBACK) -> None:
        self._lookback = lookback
        self._history: dict[str, deque[tuple[str, str, bool]]] = {}

    def record_step(self, run_id: str, agent_id: str, tool_call_signature: str, progressed: bool) -> None:
        window = self._history.setdefault(run_id, deque(maxlen=self._lookback))
        window.append((agent_id, tool_call_signature, progressed))

    def detect_repeated_no_progress(self, run_id: str) -> bool:
        window = self._history.get(run_id)
        if window is None or len(window) < self._lookback:
            return False
        first_signature = (window[0][0], window[0][1])
        return all(
            (agent_id, signature) == first_signature and not progressed
            for agent_id, signature, progressed in window
        )


class InMemoryFailureCounterStore:
    """Tracks a per-`(runId, agentId)` consecutive-failure counter, reset
    to zero on any non-FAILED result.
    """

    def __init__(self, threshold: int) -> None:
        self._threshold = threshold
        self._counts: dict[tuple[str, str], int] = {}

    def record_result(self, run_id: str, agent_id: str, status: SpokeResultStatus) -> None:
        key = (run_id, agent_id)
        if status == SpokeResultStatus.FAILED:
            self._counts[key] = self._counts.get(key, 0) + 1
        else:
            self._counts[key] = 0

    def detect_consecutive_failures(self, run_id: str, agent_id: str) -> bool:
        return self._counts.get((run_id, agent_id), 0) >= self._threshold
