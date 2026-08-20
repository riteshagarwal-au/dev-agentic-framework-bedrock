"""Router-specific exceptions."""

from __future__ import annotations


class RunHalt(Exception):
    """Raised by `resolve_model` when the escalation ladder is exhausted
    or the Opus gate denies escalation — the caller (Hub) must halt the
    run and raise a HITL alert, never silently continue (design.md
    Algorithm 1 postconditions).
    """
