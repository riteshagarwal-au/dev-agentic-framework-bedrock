"""BudgetCeiling and RunCounters — the data backing the Cost/Budget
Counter Hook (design.md Component 3, "Model 2: RunCounters").

Both are modeled as plain, immutable-by-convention value objects: no
methods that mutate hidden state, matching Requirement 4.4's data-model
portion ("preCheck SHALL NOT mutate any run state") and design.md's
Algorithm 2 note that `preCheck` is "read-only / side-effect-free" — the
mutation path (`recordUsage`, Task 8.2) lives in the repository/hook layer
(Task 5.3 / 8.x), not on these models.
"""

from __future__ import annotations

from pydantic import ConfigDict, Field

from daf.models.common import DafBaseModel
from daf.models.types import RunId


class BudgetCeiling(DafBaseModel):
    """Per-run hard caps (design.md Model 2).

    design.md: "BudgetCeiling values are hardcoded config in Phase 1 ...
    not derived or learned." All fields are non-negative; a ceiling of 0
    is legal (degenerate "no budget" case) and simply means every
    `preCheck` for that dimension halts immediately.
    """

    max_total_tokens: int = Field(ge=0, alias="maxTotalTokens")
    max_cost_usd: float = Field(ge=0.0, alias="maxCostUsd")
    max_wall_clock_ms: int = Field(ge=0, alias="maxWallClockMs")
    max_steps: int = Field(ge=0, alias="maxSteps")
    max_opus_invocations: int = Field(ge=0, alias="maxOpusInvocations")

    model_config = ConfigDict(extra="forbid", validate_assignment=True, populate_by_name=True)


class RunCounters(DafBaseModel):
    """Running usage totals for a single run (design.md Model 2).

    design.md: "All counters are monotonically increasing within a run;
    never decremented." That invariant is enforced by the atomic-increment
    repository operation (Task 5.3), not by this model — the model itself
    only enforces the non-negativity of each field's *value*, since a
    non-negative field alone can't express "never decreases over time"
    without tracking prior state.
    """

    run_id: RunId = Field(alias="runId")
    total_tokens_in: int = Field(ge=0, default=0, alias="totalTokensIn")
    total_tokens_out: int = Field(ge=0, default=0, alias="totalTokensOut")
    total_wall_clock_ms: int = Field(ge=0, default=0, alias="totalWallClockMs")
    total_steps: int = Field(ge=0, default=0, alias="totalSteps")
    opus_invocations: int = Field(ge=0, default=0, alias="opusInvocations")
    estimated_cost_usd: float = Field(ge=0.0, default=0.0, alias="estimatedCostUsd")

    model_config = ConfigDict(extra="forbid", validate_assignment=True, populate_by_name=True)
