"""Deterministic Router + agentic escalation (design.md Algorithm 1, Task 7)."""

from daf.router.exceptions import RunHalt
from daf.router.policy import CONFIDENCE_THRESHOLD, MAX_SONNET_RETRIES, TASK_MODEL_POLICY
from daf.router.router import AttemptState, resolve_model

__all__ = [
    "AttemptState",
    "CONFIDENCE_THRESHOLD",
    "MAX_SONNET_RETRIES",
    "RunHalt",
    "TASK_MODEL_POLICY",
    "resolve_model",
]
