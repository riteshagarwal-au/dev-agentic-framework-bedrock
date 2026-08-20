"""Real-infra dependency wiring for the portal-facing Lambda handlers (deployment concern
flagged as out-of-scope by `handlers.py`'s `_build_default_supervisor`/`_build_default_hitl_broker`
docstrings — this module is that wiring).

Scope: the 4 portal API routes (`POST /runs`, `GET /runs/{runId}/status`,
`GET /runs/{runId}/gates`, `POST /gates/{ticketId}/decide`) only ever call
`Supervisor.start_run` / `Supervisor.get_run_status` and
`HitlApprovalBroker.get_pending_gates` / `HitlApprovalBroker.decide`. None of them call
`Supervisor.route_task`, which is the only method that touches `hook_pipeline`/`budget_hook`/
`agent_registry`. `route_task` is driven by a separate orchestrator (Step Functions /
worker Lambda, not yet built) that also needs real MCP-backed spoke agents — building those is
Phase 2 MCP-integration work, not a portal-API deployment concern. Supervisor's constructor still
requires those three arguments, so this module wires them with clearly-labelled no-op stubs
that are never exercised by the routes this Lambda actually serves.

Table names / stream ARNs are read from environment variables set by the Terraform
`portal-api` module.
"""

from __future__ import annotations

import os
from typing import Any

import boto3

from daf.budget.hook import CostBudgetHook
from daf.budget.policy import MAX_CONSECUTIVE_FAILURES
from daf.budget.stores import (
    InMemoryFailureCounterStore,
    InMemoryIdempotencyStore,
    InMemoryKillSwitchStore,
    InMemoryStepHistoryStore,
)
from daf.hitl.broker import HitlApprovalBroker
from daf.models.budget import BudgetCeiling
from daf.models.enums import HitlGateType
from daf.models.types import GateTicketId, RunId
from daf.persistence.gate_ticket_repository import GateTicketRepository
from daf.persistence.run_counters_repository import RunCountersRepository
from daf.persistence.run_state_repository import RunStateRepository
from daf.pipeline.pipeline import HookPipeline
from daf.supervisor.supervisor import Supervisor

_dynamodb = boto3.resource("dynamodb")
_step_functions = boto3.client("stepfunctions")


class _NoOpPortalNotifier:
    """Real-time portal push notification (e.g. WebSocket) isn't built yet — gate status is
    polled via `GET /runs/{runId}/gates` instead, so a missed notify has no functional impact.
    """

    def notify_gate_raised(self, *args: Any, **kwargs: Any) -> None:
        return None


class _StepFunctionsClient:
    """Thin adapter over the real boto3 Step Functions client satisfying
    `StepFunctionsClientProtocol`. State-machine ARN comes from the Terraform-provisioned
    `hitl-gate-state-machine` module (env var `HITL_STATE_MACHINE_ARN`).
    """

    def __init__(self, state_machine_arn: str) -> None:
        self._state_machine_arn = state_machine_arn

    def start_execution_and_wait_for_task_token(
        self, gate: HitlGateType, run_id: RunId, ticket_id: GateTicketId
    ) -> str:
        raise NotImplementedError(
            "Starting the HITL wait execution is triggered by the run orchestrator "
            "(route_task path), not by the portal API Lambda."
        )

    def send_task_success(self, task_token: str, result: str) -> None:
        self._step_functions_client_send("send_task_success", task_token, output=result)

    def send_task_failure(self, task_token: str, reason: str) -> None:
        self._step_functions_client_send("send_task_failure", task_token, cause=reason)

    def _step_functions_client_send(self, method: str, task_token: str, **kwargs: Any) -> None:
        getattr(_step_functions, method)(taskToken=task_token, **kwargs)


class _UnusedRunConfigProvider:
    """Only consulted by `CostBudgetHook.pre_check`, which is only reachable via
    `Supervisor.route_task` — not exposed by this Lambda's routes (see module docstring).
    """

    def get_budget_ceiling(self, run_id: str) -> BudgetCeiling:
        raise NotImplementedError("route_task is not served by the portal API Lambda.")


def _table(env_var: str) -> Any:
    return _dynamodb.Table(os.environ[env_var])


def build_supervisor() -> Supervisor:
    from daf.observability.audit_writer import JsonAuditLogWriter

    run_state_repo = RunStateRepository(_table("RUN_STATE_TABLE_NAME"))
    run_counters_repo = RunCountersRepository(_table("RUN_COUNTERS_TABLE_NAME"))
    audit_log = JsonAuditLogWriter(sink=print)

    budget_hook = CostBudgetHook(
        run_counters_repo=run_counters_repo,
        run_config_provider=_UnusedRunConfigProvider(),
        kill_switch_store=InMemoryKillSwitchStore(),
        idempotency_store=InMemoryIdempotencyStore(),
        step_history_store=InMemoryStepHistoryStore(),
        failure_counter_store=InMemoryFailureCounterStore(MAX_CONSECUTIVE_FAILURES),
    )
    hook_pipeline = HookPipeline(
        cost_budget_hook=budget_hook,
        hitl_broker=build_hitl_broker(),
        token_estimator=_UnusedTokenEstimator(),
        gate_resolver=_UnusedGateResolver(),
        attempt_state_store=_UnusedAttemptStateStore(),
        audit_log=audit_log,
        memory_manager=_NoOpMemoryManager(),
        opus_gate_for_router=None,
    )

    return Supervisor(
        run_state_repo=run_state_repo,
        run_counters_repo=run_counters_repo,
        hook_pipeline=hook_pipeline,
        budget_hook=budget_hook,
        agent_registry={},
        audit_log=audit_log,
    )


def build_hitl_broker() -> HitlApprovalBroker:
    from daf.observability.audit_writer import JsonAuditLogWriter

    return HitlApprovalBroker(
        gate_ticket_repo=GateTicketRepository(_table("GATE_TICKET_TABLE_NAME")),
        run_state_repo=RunStateRepository(_table("RUN_STATE_TABLE_NAME")),
        step_functions_client=_StepFunctionsClient(os.environ["HITL_STATE_MACHINE_ARN"]),
        portal_notifier=_NoOpPortalNotifier(),
        audit_log=JsonAuditLogWriter(sink=print),
    )


class _UnusedTokenEstimator:
    def estimate_tokens(self, envelope: Any) -> int:
        raise NotImplementedError("route_task is not served by the portal API Lambda.")


class _UnusedGateResolver:
    def find_blocking_gate(self, task_type: Any, run_id: Any) -> Any:
        raise NotImplementedError("route_task is not served by the portal API Lambda.")


class _UnusedAttemptStateStore:
    def get(self, run_id: Any, task_id: Any) -> Any:
        raise NotImplementedError("route_task is not served by the portal API Lambda.")

    def save(self, attempt_state: Any) -> None:
        raise NotImplementedError("route_task is not served by the portal API Lambda.")


class _NoOpMemoryManager:
    def summarize_and_evict(self, run_id: Any, agent_id: Any, result: Any) -> None:
        return None
