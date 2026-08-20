from daf.models.envelope import SpokeResult


class FakeAuditLog:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def write(self, event: str, payload: dict) -> None:
        self.events.append((event, payload))


class FakeMemoryManager:
    def summarize_and_evict(self, run_id, agent_id, result) -> None:
        pass


class FakeTokenEstimator:
    def estimate_tokens(self, envelope) -> int:
        return 10


class FakeGateResolver:
    def __init__(self, gate=None):
        self._gate = gate

    def find_blocking_gate(self, task_type, run_id):
        return self._gate

    def build_approval_context(self, envelope):
        from daf.models.common import ApprovalContext

        return ApprovalContext(summary="context")


class FakeOpusGate:
    def check_opus_gate(self, run_id) -> bool:
        return True


class ScriptedAgent:
    """A SpokeAgent stand-in that always returns a fixed SUCCESS result."""

    def __init__(self, agent_id, task_type, output_schema=SpokeResult):
        self.agent_id = agent_id
        self.task_type = task_type
        self.output_schema = output_schema
        self.call_count = 0

    def execute(self, envelope, tier) -> SpokeResult:
        self.call_count += 1
        from daf.models.common import ArtifactRef
        from daf.models.enums import ArtifactKind, ArtifactLocationKind, SpokeResultStatus

        return SpokeResult(
            output=ArtifactRef(
                artifactId="a1", location="s3://b/k", locationKind=ArtifactLocationKind.S3_URI, kind=ArtifactKind.OTHER
            ),
            confidence=0.95,
            tokensUsed={"tokensIn": 5, "tokensOut": 5},
            status=SpokeResultStatus.SUCCESS,
        )
