"""Unit tests for `detect_kb_conflict` (Task 13.6)."""

from __future__ import annotations

from daf.agents.kb_conflict import KbConflict, detect_kb_conflict


class TestDetectKbConflict:
    def test_matching_guidance_returns_none(self) -> None:
        assert detect_kb_conflict("use ECS Fargate", "use ECS Fargate") is None

    def test_differing_guidance_returns_kb_conflict(self) -> None:
        result = detect_kb_conflict("use ECS Fargate", "use EKS")

        assert isinstance(result, KbConflict)
        assert result.kb_guidance == "use ECS Fargate"
        assert result.aws_docs_guidance == "use EKS"
        assert result.decision == "followed_kb"
