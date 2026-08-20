"""Pipeline-specific exceptions."""

from __future__ import annotations


class HitlAlert(Exception):
    """Raised (and expected to be caught/logged, not to crash the caller)
    when the pre-invocation budget check halts a run — design.md Algorithm
    4: "RAISE HitlAlert(...)" alongside returning a FAILED `SpokeResult`.
    """
