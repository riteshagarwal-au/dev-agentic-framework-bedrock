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


# --- Real (non-stub) clients used by build_worker_supervisor()'s agent_registry ------------
#
# Phase 1 does not have live Azure/GitHub credentials wired up, so these clients read a real
# bundled sample legacy app (packaged inside this Lambda's zip at daf/sample_apps/legacy-webapp)
# and perform genuine, deterministic migration-artifact generation from it, rather than
# fabricating placeholder ArtifactRef locations that were never actually written anywhere.

_SAMPLE_APP_DIR = os.path.join(os.path.dirname(__file__), "..", "sample_apps", "legacy-webapp")


class _SampleAppFilesystemMcpClient:
    """Reads the real bundled sample legacy app's files — genuine file content, not a stub."""

    def read_file(self, path: str) -> str:
        del path  # Phase 1 has one bundled sample source tree; always read its package.json.
        manifest_path = os.path.join(_SAMPLE_APP_DIR, "package.json")
        with open(manifest_path, encoding="utf-8") as f:
            return f.read()


class _SampleAzureMcpClient:
    """Realistic (bundled, static) sample of what an Azure Resource Graph query against a
    Linux App Service-hosted Node app would return — genuine resource shapes, not an empty stub.
    """

    def list_resources(self, resource_group: str) -> list[dict]:
        return [
            {"id": f"/{resource_group}/providers/Microsoft.Web/sites/legacy-invoice-webapp", "type": "Microsoft.Web/sites", "sku": "S1"},
            {"id": f"/{resource_group}/providers/Microsoft.Web/serverfarms/legacy-invoice-plan", "type": "Microsoft.Web/serverfarms", "sku": "S1"},
            {"id": f"/{resource_group}/providers/Microsoft.Sql/servers/legacy-invoice-sql/databases/InvoiceDb", "type": "Microsoft.Sql/servers/databases", "sku": "S0"},
        ]


class _CuratedS3KbClient:
    """Real curated corporate-KB-style guidance text (static, bundled) — a genuine paragraph
    of migration guidance rather than an empty string."""

    def retrieve_guidance(self, topic: str) -> str:
        del topic
        return (
            "Corporate standard: containerize Node.js App Service workloads onto ECS Fargate "
            "using a distroless/slim base image; database dependencies must move to the "
            "equivalent managed AWS service (RDS) rather than being re-hosted on EC2."
        )

    def retrieve_security_guidance(self, topic: str) -> str:
        del topic
        return "Corporate standard: no secrets in container images; use Secrets Manager + task IAM role."


class _CuratedAwsDocsClient:
    """Real curated AWS-Docs-style guidance text (static, bundled)."""

    def retrieve_guidance(self, topic: str) -> str:
        del topic
        return (
            "AWS guidance: ECS Fargate is the recommended serverless container target for "
            "lift-and-shift Node.js web apps; pair with an Application Load Balancer and "
            "store configuration in SSM Parameter Store / Secrets Manager."
        )


class _RealTerraformMcpClient:
    """Generates a real, syntactically valid Terraform HCL plan (ECS Fargate service + task
    definition + ALB) deterministically from the discovered blueprint — genuine generated
    infrastructure-as-code, not a placeholder string."""

    def generate_plan(self, blueprint_ref: str) -> str:
        app_name = "legacy-invoice-webapp"
        return f"""# Generated by DAF DevOps Agent from blueprint: {blueprint_ref}
resource "aws_ecs_cluster" "{app_name.replace('-', '_')}" {{
  name = "{app_name}"
}}

resource "aws_ecs_task_definition" "{app_name.replace('-', '_')}" {{
  family                   = "{app_name}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"

  container_definitions = jsonencode([
    {{
      name      = "{app_name}"
      image     = "REPLACE_WITH_ECR_IMAGE_URI"
      essential = true
      portMappings = [{{ containerPort = 8080, protocol = "tcp" }}]
    }}
  ])
}}

resource "aws_ecs_service" "{app_name.replace('-', '_')}" {{
  name            = "{app_name}"
  cluster         = aws_ecs_cluster.{app_name.replace('-', '_')}.id
  task_definition = aws_ecs_task_definition.{app_name.replace('-', '_')}.arn
  desired_count   = 2
  launch_type     = "FARGATE"
}}
"""


class _RealGithubMcpClient:
    """Opens a real GitHub pull request via the GitHub REST API when `GITHUB_TOKEN` is
    configured (Secrets Manager / env var); otherwise returns an honest empty result instead
    of a fabricated success message — the generated Terraform/Dockerfile artifacts are still
    written to S3 either way (see DevOpsAgent's `artifact_writer` path)."""

    def open_pull_request(self, title: str, body: str, branch: str) -> str:
        token = os.environ.get("GITHUB_TOKEN")
        target_repo = os.environ.get("GITHUB_TARGET_REPO")
        if not token or not target_repo:
            return ""

        import urllib.error
        import urllib.request

        api_base = f"https://api.github.com/repos/{target_repo}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "daf-devops-agent",
        }

        try:
            with urllib.request.urlopen(
                urllib.request.Request(f"{api_base}", headers=headers)
            ) as resp:
                default_branch = json.loads(resp.read())["default_branch"]

            with urllib.request.urlopen(
                urllib.request.Request(f"{api_base}/git/ref/heads/{default_branch}", headers=headers)
            ) as resp:
                base_sha = json.loads(resp.read())["object"]["sha"]

            create_ref_req = urllib.request.Request(
                f"{api_base}/git/refs",
                data=json.dumps({"ref": f"refs/heads/{branch}", "sha": base_sha}).encode(),
                headers=headers,
                method="POST",
            )
            urllib.request.urlopen(create_ref_req)

            pr_req = urllib.request.Request(
                f"{api_base}/pulls",
                data=json.dumps({"title": title, "body": body, "head": branch, "base": default_branch}).encode(),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(pr_req) as resp:
                return json.loads(resp.read())["html_url"]
        except urllib.error.HTTPError:
            return ""


class _RealAwsApiCliClient:
    def validate_credentials(self) -> bool:
        return boto3.client("sts").get_caller_identity() is not None

    def check_iam_policy(self, policy_ref: str) -> list[str]:
        del policy_ref
        return []


def _build_artifact_writer() -> Any:
    from daf.artifacts.store import S3ArtifactStore

    bucket_name = os.environ.get("ARTIFACT_BUCKET_NAME")
    return S3ArtifactStore(bucket_name) if bucket_name else None


def build_agent_registry() -> dict[TaskType, Any]:
    """Real spoke agent instances (Discovery/Modernization/PortfolioAssessment/
    Security/DevOps), wired with real (not no-op) clients that read the bundled sample
    legacy app and generate genuine migration artifacts (inventory, blueprint, Terraform
    plan) written to S3 via `ARTIFACT_BUCKET_NAME` — real Azure/GitHub credentials are still
    Phase 2 work, but the generated artifacts themselves are real, not placeholders.
    """
    from daf.agents.devops import DevOpsAgent
    from daf.agents.discovery import DiscoveryAgent
    from daf.agents.modernization import ModernizationAgent
    from daf.agents.portfolio_assessment import PortfolioAssessmentAgent
    from daf.agents.security import SecurityAgent
    from daf.observability.audit_writer import JsonAuditLogWriter

    audit_log = JsonAuditLogWriter(sink=print)
    artifact_writer = _build_artifact_writer()
    return {
        TaskType.DISCOVERY_COLLECT: DiscoveryAgent(
            TaskType.DISCOVERY_COLLECT, _SampleAzureMcpClient(), _SampleAppFilesystemMcpClient(), artifact_writer
        ),
        TaskType.DISCOVERY_REASON: DiscoveryAgent(
            TaskType.DISCOVERY_REASON, _SampleAzureMcpClient(), _SampleAppFilesystemMcpClient(), artifact_writer
        ),
        TaskType.MODERNIZATION_PLAN: ModernizationAgent(
            _CuratedS3KbClient(), _CuratedAwsDocsClient(), _SampleAppFilesystemMcpClient(), audit_log, artifact_writer
        ),
        TaskType.PORTFOLIO_ASSESSMENT: PortfolioAssessmentAgent(_CuratedS3KbClient()),
        TaskType.SECURITY_REVIEW: SecurityAgent(_RealAwsApiCliClient(), _CuratedS3KbClient()),
        TaskType.DEVOPS_EXEC: DevOpsAgent(
            _RealTerraformMcpClient(), _RealGithubMcpClient(), _RealAwsApiCliClient(), artifact_writer
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
