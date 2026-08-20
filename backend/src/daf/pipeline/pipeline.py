"""`invokeSpoke` — the pre/post agent-invocation hook pipeline composing
Algorithms 1-3 (Tasks 10.1-10.3).

Design ref: design.md "Algorithm 4: Pre/Post Agent-Invocation Hook Pipeline".

Two intentional simplifications versus the design.md pseudocode, called
out explicitly because they affect how a caller (the Supervisor, Task 12)
must use this class:

1. **HITL wait is not synchronous.** design.md's pseudocode shows
   `AWAIT StepFunctions resume signal for ticketId` inline inside
   `invokeSpoke`. In the real Step-Functions-task-token architecture
   (Component 4), that wait is durable and happens *outside* any single
   Lambda invocation: `raise_gate` returns immediately once the ticket is
   persisted, and the invocation that eventually resumes happens as a
   separate call once `HitlApprovalBroker.decide()` sends the task
   token result. This class models that faithfully: when a blocking gate
   is found, `invoke_spoke` raises the gate and returns a `SpokeResult`
   with `status=PARTIAL` and a ticket ID in `notes`, rather than blocking.
   The caller is responsible for re-invoking `invoke_spoke` (with the
   pending gate already resolved) once the gate is decided.
2. **`RAISE HitlAlert(...)` immediately followed by `RETURN`** in the
   budget-halt branch is contradictory as literal pseudocode (the return
   is unreachable after a raise). This implementation raises `HitlAlert`
   the caller must catch, and never returns a "fake" `SpokeResult` from
   that branch — the caller receiving a raised `HitlAlert` is what
   signals the halt, so there's nothing to fall through to.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from pydantic import BaseModel

from daf.budget.hook import CostBudgetHook
from daf.hitl.broker import HitlApprovalBroker
from daf.models.common import ApprovalContext
from daf.models.enums import HitlGateType, SpokeResultStatus, TaskType
from daf.models.envelope import SpokeResult, TaskEnvelope
from daf.models.types import AgentId, RunId, TaskId
from daf.pipeline.exceptions import HitlAlert
from daf.router.exceptions import RunHalt
from daf.router.policy import CONFIDENCE_THRESHOLD
from daf.router.router import AttemptState, record_outcome, resolve_model
from daf.agents.validation import OutputSchemaValidationError, validate_output_schema

logger = logging.getLogger(__name__)


class SpokeAgentProtocol(Protocol):
    """What the pipeline needs from a concrete spoke agent — a superset of
    the plain `SpokeAgent` ABC (Task 6.2) that also exposes the metadata
    the pipeline itself needs (`agent_id`, `task_type`, `output_schema`)
    and accepts the resolved model tier at call time, per design.md
    Algorithm 4's `agent.execute(envelope, tier)`.
    """

    agent_id: AgentId
    task_type: TaskType
    output_schema: type[BaseModel]

    def execute(self, envelope: TaskEnvelope, tier: Any) -> SpokeResult: ...


class TokenEstimator(Protocol):
    def estimate_tokens(self, envelope: TaskEnvelope) -> int: ...


class BlockingGateResolver(Protocol):
    """`findBlockingGate(agent.taskType, runId)` — the mapping from task
    type to the specific HITL gate it must clear, if any.
    """

    def find_blocking_gate(self, task_type: TaskType, run_id: RunId) -> HitlGateType | None: ...

    def build_approval_context(self, envelope: TaskEnvelope) -> ApprovalContext: ...


class AttemptStateStore(Protocol):
    def get(self, run_id: RunId, task_id: TaskId) -> AttemptState: ...

    def save(self, attempt_state: AttemptState) -> None: ...


class AuditLog(Protocol):
    def write(self, event: str, payload: dict) -> None: ...


class MemoryManager(Protocol):
    """`Memory.summarizeAndEvict(runId, agentId, rawResult)` (design.md
    Algorithm 4 post-invocation) — AgentCore Memory summarization, out of
    scope for this pipeline's own logic beyond calling it.
    """

    def summarize_and_evict(self, run_id: RunId, agent_id: AgentId, result: SpokeResult) -> None: ...


class InMemoryAttemptStateStore:
    """Reference in-memory `AttemptStateStore` (see Task 8's stores for the
    same "in-memory reference implementation" pattern)."""

    def __init__(self) -> None:
        self._states: dict[tuple[RunId, TaskId], AttemptState] = {}

    def get(self, run_id: RunId, task_id: TaskId) -> AttemptState:
        return self._states.get((run_id, task_id)) or AttemptState(run_id=run_id, task_id=task_id)

    def save(self, attempt_state: AttemptState) -> None:
        self._states[(attempt_state.run_id, attempt_state.task_id)] = attempt_state


class HookPipeline:
    """`invokeSpoke` (design.md Algorithm 4)."""

    def __init__(
        self,
        cost_budget_hook: CostBudgetHook,
        hitl_broker: HitlApprovalBroker,
        token_estimator: TokenEstimator,
        gate_resolver: BlockingGateResolver,
        attempt_state_store: AttemptStateStore,
        audit_log: AuditLog,
        memory_manager: MemoryManager,
        opus_gate_for_router: Any,
    ) -> None:
        self._budget = cost_budget_hook
        self._hitl = hitl_broker
        self._token_estimator = token_estimator
        self._gate_resolver = gate_resolver
        self._attempt_states = attempt_state_store
        self._audit = audit_log
        self._memory = memory_manager
        self._opus_gate_for_router = opus_gate_for_router

    def invoke_spoke(self, agent: SpokeAgentProtocol, envelope: TaskEnvelope, run_id: RunId) -> SpokeResult:
        # TaskEnvelope (Task 6.1) has no dedicated `taskId` field distinct
        # from `task` (design.md's pseudocode references `envelope.taskId`);
        # `envelope.task` is used as the task identity here.
        task_id = TaskId(envelope.task)

        # ---- PRE-INVOCATION ----
        budget_decision = self._budget.pre_check(run_id, self._token_estimator.estimate_tokens(envelope))
        if budget_decision.status.value == "HALT":
            self._budget.set_kill_switch(run_id, True)
            raise HitlAlert(f"budget breach: {budget_decision.reason}")

        pending_gate = self._gate_resolver.find_blocking_gate(agent.task_type, run_id)
        if pending_gate is not None:
            ticket_id = self._hitl.raise_gate(
                pending_gate, run_id, self._gate_resolver.build_approval_context(envelope)
            )
            return SpokeResult(
                output=envelope.inputs[next(iter(envelope.inputs))] if envelope.inputs else _empty_ref(),
                confidence=0.0,
                tokensUsed={"tokensIn": 0, "tokensOut": 0},
                status=SpokeResultStatus.PARTIAL,
                notes=f"awaiting HITL gate {pending_gate.value}: ticket {ticket_id}",
            )

        attempt_state = self._attempt_states.get(run_id, task_id)
        try:
            tier = resolve_model(agent.task_type, attempt_state, self._opus_gate_for_router)
        except RunHalt as exc:
            self._budget.set_kill_switch(run_id, True)
            raise HitlAlert(str(exc)) from exc

        # ---- INVOCATION ----
        raw_result = agent.execute(envelope, tier)

        # ---- POST-INVOCATION ----
        try:
            validated = validate_output_schema(raw_result, agent.output_schema)
        except OutputSchemaValidationError:
            return SpokeResult(
                output=raw_result.output if isinstance(raw_result, SpokeResult) else _empty_ref(),
                confidence=0.0,
                tokensUsed={"tokensIn": 0, "tokensOut": 0},
                status=SpokeResultStatus.FAILED,
                notes="schema validation failed",
            )

        self._budget.record_usage(
            run_id,
            agent.agent_id,
            tokens_in=validated.tokens_used.tokens_in,
            tokens_out=validated.tokens_used.tokens_out,
            wall_clock_ms=0,
            idempotency_key=f"{envelope.trace_id}:{attempt_state.attempt_number}",
            spoke_result_status=validated.status,
            tool_call_signature=f"{agent.agent_id}:{envelope.task}",
            progressed=True,
        )
        self._audit.write(
            "agent_invocation_complete",
            {"runId": run_id, "agentId": agent.agent_id, "status": validated.status.value, "traceId": envelope.trace_id},
        )
        self._memory.summarize_and_evict(run_id, agent.agent_id, validated)

        succeeded = validated.confidence >= CONFIDENCE_THRESHOLD
        new_attempt_state = record_outcome(attempt_state, tier, validated.confidence, succeeded)
        self._attempt_states.save(new_attempt_state)

        if not succeeded:
            return self.invoke_spoke(agent, envelope, run_id)

        return validated


def _empty_ref():
    from daf.models.common import ArtifactRef
    from daf.models.enums import ArtifactKind, ArtifactLocationKind

    return ArtifactRef(
        artifactId="none", location="none", locationKind=ArtifactLocationKind.DYNAMODB_KEY, kind=ArtifactKind.OTHER
    )
