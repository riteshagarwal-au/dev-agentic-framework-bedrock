from daf.models.envelope import SpokeResult


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


class FakeAuditLog:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def write(self, event: str, payload: dict) -> None:
        self.events.append((event, payload))


class FakeMemoryManager:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def summarize_and_evict(self, run_id, agent_id, result: SpokeResult) -> None:
        self.calls.append((run_id, agent_id, result))


class FakeOpusGate:
    def check_opus_gate(self, run_id) -> bool:
        return True


class FakeAgent:
    """Returns a scripted sequence of SpokeResults, one per call."""

    def __init__(self, agent_id, task_type, output_schema, results: list[SpokeResult]):
        self.agent_id = agent_id
        self.task_type = task_type
        self.output_schema = output_schema
        self._results = list(results)
        self.call_count = 0

    def execute(self, envelope, tier) -> SpokeResult:
        self.call_count += 1
        return self._results[min(self.call_count - 1, len(self._results) - 1)]
