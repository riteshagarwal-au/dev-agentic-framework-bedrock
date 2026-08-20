"""Supervisor-specific exceptions."""

from __future__ import annotations


class RunNotFoundError(Exception):
    """Raised when a `run_id` has no persisted `RunState`."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"No RunState found for run_id {run_id!r}")


class TerminalRunStateError(Exception):
    """Raised by `route_task` when the run is already HALTED/COMPLETED/FAILED
    and cannot accept further routing.
    """

    def __init__(self, run_id: str, status: str) -> None:
        self.run_id = run_id
        self.status = status
        super().__init__(f"Run {run_id!r} is in terminal status {status!r}; cannot route further tasks")
