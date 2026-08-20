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

import json
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
from daf.models.enums import HitlGateType, TaskType
from daf.models.types import GateTicketId, RunId
from daf.persistence.gate_ticket_repository import GateTicketRepository
from daf.persistence.run_counters_repository import RunCountersRepository
from daf.persistence.run_state_repository import RunStateRepository
from daf.persistence.serialization import from_dynamodb_item, to_dynamodb_item
from daf.pipeline.pipeline import HookPipeline, InMemoryAttemptStateStore
from daf.supervisor.supervisor import Supervisor

_dynamodb = boto3.resource("dynamodb")
_step_functions = boto3.client("stepfunctions")

# Phase 1 hardcoded default — used only when a run's own budgetCeiling
# hasn't been persisted yet (defense-in-depth; start_run always persists
# one via `persist_budget_ceiling`).
_DEFAULT_BUDGET_CEILING = BudgetCeiling(
    maxTotalTokens=1_000_000,
    maxCostUsd=50.0,
    maxWallClockMs=3_600_000,
    maxSteps=20,
    maxOpusInvocations=3,
)


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


def _budget_ceiling_item_key(run_id: str) -> str:
    # A separate item (composite "key") in the same table rather than an extra attribute
    # merged onto the RunState item itself — RunState.model_validate uses extra="forbid"
    # (see daf.models.run.RunState), so any unmodeled attribute on that item breaks every
    # future read of the run's state.
    return f"{run_id}#budgetCeiling"


def persist_budget_ceiling(run_id: str, budget_ceiling: BudgetCeiling) -> None:
    """Persists the run's BudgetCeiling as its own item in the RunState table so the run
    worker's `_DynamoRunConfigProvider` can look it up later — RunState itself has no
    budgetCeiling field (see `daf.models.run.RunState`).
    """
    _table("RUN_STATE_TABLE_NAME").put_item(
        Item=to_dynamodb_item(
            {"runId": _budget_ceiling_item_key(run_id), "budgetCeiling": budget_ceiling.model_dump(by_alias=True, mode="json")}
        ),
    )


def trigger_run_worker(run_id: str) -> None:
    """Asynchronously invokes the run-worker Lambda to advance `run_id` through
    `Supervisor.route_task` — called after `start_run` and after each HITL gate decision.
    """
    boto3.client("lambda").invoke(
        FunctionName=os.environ["WORKER_FUNCTION_NAME"],
        InvocationType="Event",
        Payload=json.dumps({"runId": run_id}).encode(),
    )


def get_run_id_for_ticket(ticket_id: str) -> str | None:
    """Looks up the `runId` a gate ticket belongs to, so `decide_gate` can re-trigger the
    run-worker Lambda for the right run after a HITL decision (the decide response body only
    echoes back `ticketId`/`decision`, not `runId`)."""
    ticket = GateTicketRepository(_table("GATE_TICKET_TABLE_NAME")).get(ticket_id)
    return ticket.run_id if ticket is not None else None


class _DynamoRunConfigProvider:
    """Real `RunConfigProvider` (see `daf.budget.hook.RunConfigProvider`) backed by the
    separate item `persist_budget_ceiling` writes into the RunState table.
    """

    def get_budget_ceiling(self, run_id: str) -> BudgetCeiling:
        item = _table("RUN_STATE_TABLE_NAME").get_item(Key={"runId": _budget_ceiling_item_key(run_id)}).get("Item")
        if item and "budgetCeiling" in item:
            return BudgetCeiling.model_validate(from_dynamodb_item(item["budgetCeiling"]))
        return _DEFAULT_BUDGET_CEILING


class _NoGateResolver:
    """Phase 1 stub `BlockingGateResolver`: no HITL gates are wired to the run-worker Lambda
    yet, since raising a real gate requires the Step Functions waitForTaskToken execution to
    be started from *inside* this worker (not just returning a token from `start_execution`,
    which `_StepFunctionsClient.start_execution_and_wait_for_task_token` still doesn't
    implement). Tracked as a known Phase 1 gap — see repo memory / continuation notes.
    """

    def find_blocking_gate(self, task_type: Any, run_id: Any) -> Any:
        return None

    def build_approval_context(self, envelope: Any) -> Any:
        raise NotImplementedError("never called: find_blocking_gate always returns None")


class _SimpleTokenEstimator:
    """Rough token estimate (chars / 4) — good enough to feed `CostBudgetHook.pre_check`
    until real Bedrock model invocations replace the stub agents' fixed-size responses.
    """

    def estimate_tokens(self, envelope: Any) -> int:
        return max(len(str(envelope.inputs)) // 4, 16)


class _NoOpAzureMcpClient:
    def list_resources(self, resource_group: str) -> list[dict]:
        return []


class _NoOpFilesystemMcpClient:
    def read_file(self, path: str) -> str:
        return ""


class _NoOpS3KbClient:
    def retrieve_guidance(self, topic: str) -> str:
        return ""

    def retrieve_security_guidance(self, topic: str) -> str:
        return ""


class _NoOpAwsDocsClient:
    def retrieve_guidance(self, topic: str) -> str:
        return ""


class _NoOpTerraformMcpClient:
    def generate_plan(self, blueprint_ref: str) -> str:
        return ""


class _NoOpGithubMcpClient:
    def open_pull_request(self, title: str, body: str, branch: str) -> str:
        return ""


class _NoOpAwsApiCliClient:
    def validate_credentials(self) -> bool:
        return True

    def check_iam_policy(self, policy_ref: str) -> list[str]:
        return []


def build_agent_registry() -> dict[TaskType, Any]:
    """Real spoke agent instances (Discovery/Modernization/PortfolioAssessment/
    Security/DevOps), each wired with no-op MCP client stubs — Phase 1 does not yet
    have real Azure/AWS-Docs/S3-KB/Terraform/GitHub MCP integrations (Phase 2 work),
    so agent logic runs but produces placeholder output rather than a real migration
    analysis. This is enough to exercise the full task-graph/hook-pipeline/budget/router
    plumbing end-to-end.
    """
    from daf.agents.devops import DevOpsAgent
    from daf.agents.discovery import DiscoveryAgent
    from daf.agents.modernization import ModernizationAgent
    from daf.agents.portfolio_assessment import PortfolioAssessmentAgent
    from daf.agents.security import SecurityAgent
    from daf.observability.audit_writer import JsonAuditLogWriter

    audit_log = JsonAuditLogWriter(sink=print)
    return {
        TaskType.DISCOVERY_COLLECT: DiscoveryAgent(
            TaskType.DISCOVERY_COLLECT, _NoOpAzureMcpClient(), _NoOpFilesystemMcpClient()
        ),
        TaskType.DISCOVERY_REASON: DiscoveryAgent(
            TaskType.DISCOVERY_REASON, _NoOpAzureMcpClient(), _NoOpFilesystemMcpClient()
        ),
        TaskType.MODERNIZATION_PLAN: ModernizationAgent(
            _NoOpS3KbClient(), _NoOpAwsDocsClient(), _NoOpFilesystemMcpClient(), audit_log
        ),
        TaskType.PORTFOLIO_ASSESSMENT: PortfolioAssessmentAgent(_NoOpS3KbClient()),
        TaskType.SECURITY_REVIEW: SecurityAgent(_NoOpAwsApiCliClient(), _NoOpS3KbClient()),
        TaskType.DEVOPS_EXEC: DevOpsAgent(
            _NoOpTerraformMcpClient(), _NoOpGithubMcpClient(), _NoOpAwsApiCliClient()
        ),
    }


class _OpusGateAdapter:
    """Adapts `CostBudgetHook.check_opus_gate` (returns `OpusGateDecision`) to the
    `OpusGateProtocol` the Router expects (`-> bool`)."""

    def __init__(self, budget_hook: CostBudgetHook) -> None:
        self._budget_hook = budget_hook

    def check_opus_gate(self, run_id: str) -> bool:
        from daf.budget.models import GateStatus

        return self._budget_hook.check_opus_gate(run_id).status == GateStatus.ALLOWED


def build_worker_supervisor() -> Supervisor:
    """The full `Supervisor` used by the run-worker Lambda (`daf.portal_api.orchestrator`) —
    unlike `build_supervisor()` (portal API routes, which never call `route_task`), this one
    wires a real `agent_registry`, `TokenEstimator`, `AttemptStateStore`, and
    `RunConfigProvider` so `route_task` actually executes.
    """
    from daf.observability.audit_writer import JsonAuditLogWriter

    run_state_repo = RunStateRepository(_table("RUN_STATE_TABLE_NAME"))
    run_counters_repo = RunCountersRepository(_table("RUN_COUNTERS_TABLE_NAME"))
    audit_log = JsonAuditLogWriter(sink=print)

    budget_hook = CostBudgetHook(
        run_counters_repo=run_counters_repo,
        run_config_provider=_DynamoRunConfigProvider(),
        kill_switch_store=InMemoryKillSwitchStore(),
        idempotency_store=InMemoryIdempotencyStore(),
        step_history_store=InMemoryStepHistoryStore(),
        failure_counter_store=InMemoryFailureCounterStore(MAX_CONSECUTIVE_FAILURES),
    )
    hook_pipeline = HookPipeline(
        cost_budget_hook=budget_hook,
        hitl_broker=build_hitl_broker(),
        token_estimator=_SimpleTokenEstimator(),
        gate_resolver=_NoGateResolver(),
        attempt_state_store=InMemoryAttemptStateStore(),
        audit_log=audit_log,
        memory_manager=_NoOpMemoryManager(),
        opus_gate_for_router=_OpusGateAdapter(budget_hook),
    )

    return Supervisor(
        run_state_repo=run_state_repo,
        run_counters_repo=run_counters_repo,
        hook_pipeline=hook_pipeline,
        budget_hook=budget_hook,
        agent_registry=build_agent_registry(),
        audit_log=audit_log,
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
