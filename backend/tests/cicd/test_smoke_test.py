from daf.cicd.smoke_test import run_smoke_test
from daf.models.types import RunId


class FakeCheck:
    def __init__(self, passed: bool, detail: str = "ok") -> None:
        self._passed = passed
        self._detail = detail
        self.calls = 0

    def check(self) -> tuple[bool, str]:
        self.calls += 1
        return self._passed, self._detail


class FakeAuditLog:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def write(self, event: str, payload: dict) -> None:
        self.events.append((event, payload))


class FakeAlerter:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, result) -> None:
        self.calls.append(result)


def test_both_checks_pass():
    health = FakeCheck(True)
    functional = FakeCheck(True)
    audit = FakeAuditLog()
    alerter = FakeAlerter()

    result = run_smoke_test(health, functional, audit, RunId("run-1"), on_failure_alert=alerter)

    assert result.passed is True
    assert result.health_check_passed is True
    assert result.functional_check_passed is True
    assert len(audit.events) == 1
    assert audit.events[0][0] == "smoke_test_passed"
    assert alerter.calls == []
    assert health.calls == 1
    assert functional.calls == 1


def test_health_check_fails():
    health = FakeCheck(False, "unhealthy")
    functional = FakeCheck(True)
    audit = FakeAuditLog()
    alerter = FakeAlerter()

    result = run_smoke_test(health, functional, audit, RunId("run-1"), on_failure_alert=alerter)

    assert result.passed is False
    assert result.health_check_passed is False
    assert len(audit.events) == 1
    assert audit.events[0][0] == "smoke_test_failed"
    assert len(alerter.calls) == 1
    assert health.calls == 1
    assert functional.calls == 0


def test_functional_check_fails():
    health = FakeCheck(True)
    functional = FakeCheck(False, "broken")
    audit = FakeAuditLog()
    alerter = FakeAlerter()

    result = run_smoke_test(health, functional, audit, RunId("run-1"), on_failure_alert=alerter)

    assert result.passed is False
    assert result.health_check_passed is True
    assert result.functional_check_passed is False
    assert len(audit.events) == 1
    assert audit.events[0][0] == "smoke_test_failed"
    assert len(alerter.calls) == 1
    assert health.calls == 1
    assert functional.calls == 1
