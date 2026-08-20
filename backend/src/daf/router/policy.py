"""Task-type → default model tier policy table (Task 7.1).

Design ref: design.md Algorithm 1 "TASK_MODEL_POLICY[taskType]" (source
§5.2), Component 5 agent table (per-agent default model / escalation
notes).

`TASK_MODEL_POLICY` must be exhaustive over every `TaskType` value —
enforced by `test_policy_table_is_exhaustive` (Task 7.3) and by
`resolve_model` raising `KeyError` (never a silent fallback) if it isn't.
"""

from __future__ import annotations

from types import MappingProxyType

from daf.models.enums import ModelTier, TaskType

TASK_MODEL_POLICY: MappingProxyType[TaskType, ModelTier] = MappingProxyType(
    {
        TaskType.DISCOVERY_COLLECT: ModelTier.HAIKU,
        TaskType.DISCOVERY_REASON: ModelTier.SONNET,
        TaskType.DEVOPS_EXEC: ModelTier.HAIKU,
        TaskType.SECURITY_REVIEW: ModelTier.SONNET,
        TaskType.MODERNIZATION_PLAN: ModelTier.SONNET,
        TaskType.PORTFOLIO_ASSESSMENT: ModelTier.SONNET,
        TaskType.PR_REVIEW: ModelTier.HAIKU,
    }
)

# Phase 1 hardcoded config (design.md: BudgetCeiling values are similarly
# "hardcoded config in Phase 1 ... not derived or learned").
CONFIDENCE_THRESHOLD = 0.7
MAX_SONNET_RETRIES = 2
