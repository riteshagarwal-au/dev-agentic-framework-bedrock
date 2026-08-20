"""Shared KB-vs-AWS-Docs conflict detection helper (Task 13.6).

design.md: on conflict between the corporate knowledge base and AWS
Documentation MCP guidance, an agent "follows the KB guidance" and the
pipeline writes a dedicated `kb_conflict_flagged` audit event. This module
only owns the detection half of that rule — a small, deterministic,
Phase 1 stub-level comparison — not the audit-event-writing half, which is
the hook pipeline's responsibility (out of scope here).

Deliberately shared (not private to the Modernization Agent) because any
other agent retrieving both an S3 KB guidance string and an AWS Docs
guidance string for the same topic can reuse it (e.g. a future PR-Reviewer
or Portfolio Assessment extension).
"""

from __future__ import annotations

from daf.models.common import DafBaseModel


class KbConflict(DafBaseModel):
    """Structured record of a detected KB vs AWS Docs guidance conflict."""

    kb_guidance: str
    aws_docs_guidance: str
    decision: str = "followed_kb"


def detect_kb_conflict(kb_guidance: str, aws_docs_guidance: str) -> KbConflict | None:
    """Return a `KbConflict` if `kb_guidance` and `aws_docs_guidance` differ.

    Phase 1 stub-level detector: exact string equality is treated as
    "consistent" (returns `None`); any difference is treated as a
    conflict, always resolved by following the KB guidance per design.md.
    Real semantic diffing is out of scope for Phase 1.
    """
    if kb_guidance == aws_docs_guidance:
        return None
    return KbConflict(kb_guidance=kb_guidance, aws_docs_guidance=aws_docs_guidance)
