"""SpokeAgent interface and output-schema validation (Task 6.2).

design.md Component 5 "Common interface"; Algorithm 4 post-invocation
"Output schema validation" step.

See:
- .kiro/specs/daf-phase1-foundations/design.md#component-5
- .kiro/specs/daf-phase1-foundations/requirements.md (Requirement 2.1)
"""

from daf.agents.base import SpokeAgent
from daf.agents.validation import OutputSchemaValidationError, validate_output_schema

__all__ = [
    "SpokeAgent",
    "OutputSchemaValidationError",
    "validate_output_schema",
]
