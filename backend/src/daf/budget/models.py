"""Result types for the Cost/Budget Counter Hook (design.md `BudgetDecision`,
`OpusGateDecision`).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class DecisionStatus(StrEnum):
    OK = "OK"
    HALT = "HALT"


class GateStatus(StrEnum):
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"


class BudgetDecision(BaseModel):
    """`preCheck`'s return type (design.md Algorithm 2)."""

    status: DecisionStatus
    reason: str = ""

    model_config = ConfigDict(extra="forbid")


class OpusGateDecision(BaseModel):
    """`checkOpusGate`'s return type (design.md Algorithm 2)."""

    status: GateStatus
    reason: str = ""

    model_config = ConfigDict(extra="forbid")
