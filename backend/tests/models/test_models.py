"""Basic construction tests for the shared Pydantic models (Task 6.1).

These confirm each model can be built with valid data and that the three
headline validation rules called out in Task 6.1 are enforced:
  - the ArtifactRef-only rule on TaskEnvelope.inputs
  - the Phase 1 targetPlatform restriction on RunConfig
  - the confidence bounds on SpokeResult

Exhaustive validation-rule testing (enum completeness, malformed
RunConfig/BudgetCeiling, etc.) is Task 6.3's responsibility, not this one.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from daf.models import (
    ApprovalContext,
    ArtifactKind,
    ArtifactLocationKind,
    ArtifactRef,
    AzureSourceRef,
    BudgetCeiling,
    GateTicket,
    GateTicketStatus,
    HitlGateType,
    ModelTier,
    RunConfig,
    RunCounters,
    RunState,
    RunStatus,
    SpokeResult,
    SpokeResultStatus,
    TargetPlatform,
    TaskEnvelope,
    TokenUsage,
)


def _artifact_ref(artifact_id: str = "artifact-1") -> ArtifactRef:
    return ArtifactRef(
        artifact_id=artifact_id,
        location="s3://daf-artifacts/run-1/inventory.json",
        location_kind=ArtifactLocationKind.S3_URI,
        kind=ArtifactKind.INVENTORY,
    )


def _budget_ceiling() -> BudgetCeiling:
    return BudgetCeiling(
        max_total_tokens=2_000_000,
        max_cost_usd=25.0,
        max_wall_clock_ms=3_600_000,
        max_steps=200,
        max_opus_invocations=2,
    )


class TestArtifactRef:
    def test_construction_with_valid_data(self):
        ref = _artifact_ref()
        assert ref.artifact_id == "artifact-1"
        assert ref.kind == ArtifactKind.INVENTORY
        assert ref.location_kind == ArtifactLocationKind.S3_URI


class TestTaskEnvelope:
    def test_construction_with_valid_data(self):
        envelope = TaskEnvelope(
            task="inventory-azure-source",
            inputs={"sourceInventory": _artifact_ref()},
            acceptance_criteria=["inventory covers all VMs and web apps"],
            trace_id="trace-123",
        )
        assert envelope.task == "inventory-azure-source"
        assert envelope.inputs["sourceInventory"].artifact_id == "artifact-1"
        assert envelope.trace_id == "trace-123"

    def test_construction_with_no_inputs_is_valid(self):
        envelope = TaskEnvelope(task="noop", trace_id="trace-1")
        assert envelope.inputs == {}

    def test_inputs_must_be_artifact_refs_rejects_inlined_content(self):
        """The ArtifactRef-only rule: passing raw content (a string) or an
        arbitrary dict instead of an ArtifactRef must be rejected.
        """
        with pytest.raises(ValidationError):
            TaskEnvelope(
                task="inventory-azure-source",
                inputs={"sourceInventory": "raw inlined file content, not a ref"},
                trace_id="trace-123",
            )

    def test_inputs_must_be_artifact_refs_rejects_dict_missing_fields(self):
        with pytest.raises(ValidationError):
            TaskEnvelope(
                task="inventory-azure-source",
                inputs={"sourceInventory": {"not": "an artifact ref"}},
                trace_id="trace-123",
            )


class TestSpokeResult:
    def test_construction_with_valid_data(self):
        result = SpokeResult(
            output=_artifact_ref(),
            confidence=0.95,
            tokens_used=TokenUsage(tokens_in=1200, tokens_out=340),
            status=SpokeResultStatus.SUCCESS,
            notes="inventory collection complete",
        )
        assert result.status == SpokeResultStatus.SUCCESS
        assert result.confidence == pytest.approx(0.95)

    @pytest.mark.parametrize("confidence", [0.0, 1.0, 0.5])
    def test_confidence_boundary_values_are_valid(self, confidence: float):
        result = SpokeResult(
            output=_artifact_ref(),
            confidence=confidence,
            tokens_used=TokenUsage(tokens_in=10, tokens_out=5),
            status=SpokeResultStatus.SUCCESS,
        )
        assert result.confidence == confidence

    @pytest.mark.parametrize("confidence", [-0.01, 1.01, -5.0, 100.0])
    def test_confidence_out_of_bounds_is_rejected(self, confidence: float):
        with pytest.raises(ValidationError):
            SpokeResult(
                output=_artifact_ref(),
                confidence=confidence,
                tokens_used=TokenUsage(tokens_in=10, tokens_out=5),
                status=SpokeResultStatus.SUCCESS,
            )


class TestRunConfig:
    def test_construction_with_valid_data(self):
        config = RunConfig(
            run_id="run-1",
            target_app="synthetic-app-01",
            source_env=AzureSourceRef(
                subscription_id="sub-1",
                resource_group="rg-synthetic",
                resource_name="synthetic-app-01",
            ),
            target_platform=TargetPlatform.ECS_FARGATE,
            budget_ceiling=_budget_ceiling(),
            target_repo="riteshagarwal-au/appmigration-daf",
        )
        assert config.target_platform == TargetPlatform.ECS_FARGATE

    @pytest.mark.parametrize("platform", [TargetPlatform.EKS, TargetPlatform.AZURE])
    def test_target_platform_restricted_to_ecs_fargate_in_phase_1(self, platform: TargetPlatform):
        with pytest.raises(ValidationError):
            RunConfig(
                run_id="run-1",
                target_app="synthetic-app-01",
                source_env=AzureSourceRef(
                    subscription_id="sub-1",
                    resource_group="rg-synthetic",
                    resource_name="synthetic-app-01",
                ),
                target_platform=platform,
                budget_ceiling=_budget_ceiling(),
            )


class TestRunState:
    def test_construction_with_valid_data(self):
        now = datetime.now(UTC)
        state = RunState(
            run_id="run-1",
            status=RunStatus.RUNNING,
            task_graph=[],
            current_step_index=0,
            trace_id="trace-1",
            counters=RunCounters(run_id="run-1"),
            created_at=now,
            updated_at=now,
        )
        assert state.status == RunStatus.RUNNING
        assert state.counters.run_id == "run-1"


class TestRunCounters:
    def test_construction_with_defaults(self):
        counters = RunCounters(run_id="run-1")
        assert counters.total_tokens_in == 0
        assert counters.opus_invocations == 0

    @pytest.mark.parametrize(
        "field_name",
        [
            "total_tokens_in",
            "total_tokens_out",
            "total_wall_clock_ms",
            "total_steps",
            "opus_invocations",
        ],
    )
    def test_negative_counters_are_rejected(self, field_name: str):
        with pytest.raises(ValidationError):
            RunCounters(run_id="run-1", **{field_name: -1})

    def test_negative_estimated_cost_is_rejected(self):
        with pytest.raises(ValidationError):
            RunCounters(run_id="run-1", estimated_cost_usd=-0.01)


class TestBudgetCeiling:
    def test_construction_with_valid_data(self):
        ceiling = _budget_ceiling()
        assert ceiling.max_opus_invocations == 2

    def test_negative_max_opus_invocations_is_rejected(self):
        with pytest.raises(ValidationError):
            BudgetCeiling(
                max_total_tokens=1,
                max_cost_usd=1.0,
                max_wall_clock_ms=1,
                max_steps=1,
                max_opus_invocations=-1,
            )


class TestGateTicket:
    def test_construction_with_valid_data(self):
        ticket = GateTicket(
            ticket_id="ticket-1",
            run_id="run-1",
            gate_type=HitlGateType.PLAN_FINALIZE,
            status=GateTicketStatus.PENDING,
            context=ApprovalContext(summary="Approve migration plan for synthetic-app-01"),
            raised_at=datetime.now(UTC),
            step_functions_task_token="sfn-task-token-abc",
        )
        assert ticket.status == GateTicketStatus.PENDING
        assert ticket.decided_at is None
        assert ticket.approver is None

    def test_all_seven_gate_types_are_defined(self):
        assert {member.value for member in HitlGateType} == {
            "INFRA_APPLY",
            "PR_MERGE",
            "DESTRUCTIVE_ACTION",
            "WORKER_SPINUP",
            "KB_WRITE",
            "PLAN_FINALIZE",
            "CLOUD_DEPLOY",
        }
        assert len(HitlGateType) == 7


class TestModelTier:
    def test_all_three_tiers_are_defined(self):
        assert {member.value for member in ModelTier} == {"HAIKU", "SONNET", "OPUS"}


class TestRunStatus:
    def test_all_six_statuses_are_defined(self):
        assert {member.value for member in RunStatus} == {
            "PENDING",
            "RUNNING",
            "HALTED",
            "AWAITING_HITL",
            "COMPLETED",
            "FAILED",
        }
