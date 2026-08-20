"""SpokeAgent interface — the common contract every agent implements.

design.md Component 5 "Common interface (all core agents implement this
contract)":

    INTERFACE SpokeAgent
      PROCEDURE execute(envelope: TaskEnvelope) RETURNS SpokeResult
    END INTERFACE

Requirement 2.1: "EACH core agent SHALL implement the
`SpokeAgent.execute(envelope)` interface and return a `SpokeResult`
containing `output`, `confidence`, `tokensUsed`, `status`, and `notes`."

Every concrete agent — Discovery, DevOps, Security, Modernization, and
Portfolio Assessment (Tasks 13.1-13.5), plus the on-demand PR-Reviewer
(Task 14.1) — subclasses `SpokeAgent` and implements `execute`. The
Supervisor (Task 12.x) and the pre/post agent-invocation hook pipeline
(Task 10.x) depend only on this interface, never on a concrete agent
class, so any of the six agents can be invoked polymorphically through
`invokeSpoke`/`routeTask`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from daf.models.envelope import SpokeResult, TaskEnvelope


class SpokeAgent(ABC):
    """Abstract base class every spoke agent implements.

    Subclasses must implement `execute`, which receives a bounded
    `TaskEnvelope` (never full run history — Requirement 2.2) and must
    return a `SpokeResult` (Requirement 2.1). Because `execute` is
    declared with `@abstractmethod`, `abc.ABC`'s machinery prevents both
    `SpokeAgent` itself and any subclass that omits an `execute` override
    from being instantiated — the contract is enforced at instantiation
    time, not only by convention or a runtime check this class would
    otherwise have to write itself.
    """

    @abstractmethod
    def execute(self, envelope: TaskEnvelope) -> SpokeResult:
        """Execute this agent's task and return a structured result.

        Args:
            envelope: The bounded task input (task, inputs as
                `ArtifactRef`s, acceptance criteria, trace ID) — see
                `TaskEnvelope`. Never carries full run history inline.

        Returns:
            A `SpokeResult` with `output`, `confidence`, `tokensUsed`,
            `status`, and `notes` populated, per Requirement 2.1.
        """
        raise NotImplementedError
