"""Typed string identifier aliases used throughout the DAF data models.

design.md types every identifier (RunId, TaskId, AgentId, TraceId,
GateTicketId, UserId) as a distinct type rather than a bare `str`, e.g.:

    STRUCTURE RunConfig
      runId: RunId
      ...

`typing.NewType` gives us that distinction at the type-checker level (so a
`TaskId` can't be silently passed where a `RunId` is expected) while still
behaving as a plain `str` at runtime, which is what Pydantic needs to
validate/serialize them with no extra ceremony.

Note on `runId` uniqueness/immutability (design.md Model 1 validation
rules): true DB-level uniqueness enforcement is out of scope for this data
model — it is the responsibility of the persistence layer (Task 5.2's
`RunStateRepository`, e.g. a conditional `PutItem` that fails if the key
already exists). Typing `runId` distinctly here is what makes that
enforcement point clear/discoverable at the model boundary.
"""

from typing import NewType

RunId = NewType("RunId", str)
TaskId = NewType("TaskId", str)
AgentId = NewType("AgentId", str)
TraceId = NewType("TraceId", str)
GateTicketId = NewType("GateTicketId", str)
UserId = NewType("UserId", str)
