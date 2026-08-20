"""Scripted (non-LLM) post-deploy smoke test (Task 14.6).

Design ref: design.md source §12 "post-deploy smoke test" — a deterministic
script check, not an agent/model invocation. On any failure this raises a
HITL alert via an injected `on_failure_alert` callback rather than
attempting any remediation/retry itself, matching the callback-injection
style already used for cross-cutting side effects in this repo (e.g.
`AuditLog`/`PortalNotifier` protocols in `daf.hitl.broker` and
`daf.pipeline.pipeline`).
"""

from __future__ import annotations

from typing import Callable, Protocol

from pydantic import BaseModel

from daf.models.types import RunId


class HealthCheckProtocol(Protocol):
    def check(self) -> tuple[bool, str]:
        """Returns `(passed, detail)`."""
        ...


class FunctionalCheckProtocol(Protocol):
    def check(self) -> tuple[bool, str]:
        """Returns `(passed, detail)`."""
        ...


class AuditLogProtocol(Protocol):
    def write(self, event: str, payload: dict) -> None: ...


class SmokeTestResult(BaseModel):
    passed: bool
    health_check_passed: bool
    functional_check_passed: bool
    detail: str


def run_smoke_test(
    health_check: HealthCheckProtocol,
    functional_check: FunctionalCheckProtocol,
    audit_log: AuditLogProtocol,
    run_id: RunId,
    on_failure_alert: Callable[[SmokeTestResult], None] | None = None,
) -> SmokeTestResult:
    """Run the health check, then the functional check, both deterministic
    script calls (no model invocation anywhere in this function).

    Writes exactly one audit event reporting pass/fail. On any failure
    (health OR functional), no remediation/retry is attempted here — the
    failed `SmokeTestResult` is returned and `on_failure_alert` (if given)
    is invoked so the caller can raise a HITL alert.
    """
    health_passed, health_detail = health_check.check()
    functional_passed, functional_detail = False, "skipped: health check failed"
    if health_passed:
        functional_passed, functional_detail = functional_check.check()

    passed = health_passed and functional_passed
    detail = f"health: {health_detail}; functional: {functional_detail}"
    result = SmokeTestResult(
        passed=passed,
        health_check_passed=health_passed,
        functional_check_passed=functional_passed,
        detail=detail,
    )

    audit_log.write(
        "smoke_test_passed" if passed else "smoke_test_failed",
        {"runId": run_id, **result.model_dump()},
    )

    if not passed and on_failure_alert is not None:
        on_failure_alert(result)

    return result
