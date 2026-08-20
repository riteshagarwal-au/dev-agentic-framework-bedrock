"""Run-worker Lambda entrypoint: drives `Supervisor.route_task` (Task 12.2) to completion.

Design context (see `daf.portal_api.wiring` module docstring): the portal API's 4 Lambda
routes never call `route_task` — this is the separate worker that does. It's invoked
asynchronously (fire-and-forget) by `start_run` right after a run is created, and again by
`decide_gate` after a HITL decision, so the run keeps progressing without the portal API
Lambda blocking on a long-running loop.

Known Phase 1 gap: `wiring._NoGateResolver` never raises a real HITL gate from this worker
(raising one requires the Step Functions waitForTaskToken execution to be started from here,
which isn't wired yet), so `decide_gate`'s re-trigger currently has no run-worker-raised gate
to resume from in practice. Tracked as a follow-up, not silently pretended to work.
"""

from __future__ import annotations

from typing import Any

from daf.models.types import RunId
from daf.portal_api.wiring import build_worker_supervisor
from daf.supervisor.exceptions import RunNotFoundError, TerminalRunStateError

_supervisor = build_worker_supervisor()

# Phase 1's task graph has 6 fixed nodes (see `daf.supervisor.task_graph`); cap iterations
# generously above that so a routing bug can't spin the Lambda forever within its timeout.
_MAX_ITERATIONS = 20


def run_worker_handler(event: dict, context: Any) -> dict:
    run_id = RunId(event["runId"])

    for _ in range(_MAX_ITERATIONS):
        try:
            status = _supervisor.get_run_status(run_id)
        except RunNotFoundError:
            return {"runId": run_id, "outcome": "not_found"}

        if status.value in ("HALTED", "COMPLETED", "FAILED"):
            return {"runId": run_id, "outcome": "terminal", "status": status.value}

        try:
            result = _supervisor.route_task(run_id)
        except TerminalRunStateError:
            return {"runId": run_id, "outcome": "terminal"}

        if result.status.value == "PARTIAL":
            # Awaiting a HITL gate decision — stop here; `decide_gate` re-triggers this worker.
            return {"runId": run_id, "outcome": "awaiting_gate"}

    return {"runId": run_id, "outcome": "max_iterations_reached"}
