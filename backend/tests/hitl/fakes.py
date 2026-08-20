from daf.models.gate import GateTicket
from daf.models.types import GateTicketId, RunId


class FakeStepFunctionsClient:
    def __init__(self) -> None:
        self.started: list[tuple] = []
        self.successes: list[tuple[str, str]] = []
        self.failures: list[tuple[str, str]] = []
        self._counter = 0

    def start_execution_and_wait_for_task_token(self, gate, run_id, ticket_id) -> str:
        self._counter += 1
        token = f"task-token-{self._counter}"
        self.started.append((gate, run_id, ticket_id, token))
        return token

    def send_task_success(self, task_token: str, result: str) -> None:
        self.successes.append((task_token, result))

    def send_task_failure(self, task_token: str, reason: str) -> None:
        self.failures.append((task_token, reason))


class FakePortalNotifier:
    def __init__(self) -> None:
        self.gate_raised: list[GateTicket] = []
        self.run_halted: list[tuple[RunId, str]] = []

    def notify_gate_raised(self, ticket: GateTicket) -> None:
        self.gate_raised.append(ticket)

    def notify_run_halted(self, run_id: RunId, reason: str) -> None:
        self.run_halted.append((run_id, reason))


class FakeAuditLog:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def write(self, event: str, payload: dict) -> None:
        self.events.append((event, payload))
