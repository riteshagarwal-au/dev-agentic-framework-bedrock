"""Cost/Budget Counter Hook (design.md Algorithm 2, Task 8)."""

from daf.budget.hook import CostBudgetHook
from daf.budget.models import BudgetDecision, DecisionStatus, OpusGateDecision
from daf.budget.policy import MAX_CONSECUTIVE_FAILURES, NO_PROGRESS_LOOKBACK
from daf.budget.stores import (
    InMemoryFailureCounterStore,
    InMemoryIdempotencyStore,
    InMemoryKillSwitchStore,
    InMemoryStepHistoryStore,
)

__all__ = [
    "BudgetDecision",
    "CostBudgetHook",
    "DecisionStatus",
    "InMemoryFailureCounterStore",
    "InMemoryIdempotencyStore",
    "InMemoryKillSwitchStore",
    "InMemoryStepHistoryStore",
    "MAX_CONSECUTIVE_FAILURES",
    "NO_PROGRESS_LOOKBACK",
    "OpusGateDecision",
]
