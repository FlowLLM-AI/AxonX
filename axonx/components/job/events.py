"""Canonical streaming events emitted by Jobs."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from .contracts import JobResponse


class ProgressEvent(BaseModel):
    kind: Literal["progress"] = "progress"
    name: str = Field(min_length=1)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    percentage: float | None = Field(default=None, ge=0, le=100)

    @classmethod
    def from_status(cls, status: Any) -> ProgressEvent:
        return cls.model_validate(status, from_attributes=True)


class LogEvent(BaseModel):
    kind: Literal["log"] = "log"
    content: str = ""
    start_offset: int = 0
    next_offset: int = 0
    file_size: int = 0
    has_more_before: bool = False
    has_more_after: bool = False
    reset: bool = False
    channel: str = "task"

    @classmethod
    def from_chunk(cls, chunk: Any) -> LogEvent:
        return cls.model_validate(chunk, from_attributes=True)


class ArtifactEvent(BaseModel):
    kind: Literal["artifact"] = "artifact"
    path: str
    sha256: str = ""
    size: int = 0
    media_type: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class AgentBlockPatch(BaseModel):
    operation: Literal["start", "append", "replace", "finish"]
    block_id: str = Field(min_length=1)
    block_type: Literal["thinking", "text", "tool", "system", "error"]
    delta: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentMessageEvent(BaseModel):
    kind: Literal["agent_message"] = "agent_message"
    session_id: str = Field(min_length=1)
    type_name: str
    message: dict[str, Any]
    sequence: int = Field(ge=0)
    presentation: list[AgentBlockPatch] = Field(default_factory=list)


class ResultEvent(JobResponse):
    kind: Literal["result"] = "result"

    @classmethod
    def from_response(cls, response: JobResponse) -> ResultEvent:
        return cls(
            answer=response.answer,
            success=response.success,
            metadata=response.metadata,
        )

    def response(self) -> JobResponse:
        return JobResponse(
            answer=self.answer,
            success=self.success,
            metadata=self.metadata,
        )


type JobEvent = Annotated[
    ProgressEvent | LogEvent | ArtifactEvent | AgentMessageEvent | ResultEvent,
    Field(discriminator="kind"),
]
JOB_EVENT_ADAPTER: TypeAdapter[JobEvent] = TypeAdapter(JobEvent)


async def fold_events(events: AsyncIterator[JobEvent]) -> JobResponse:
    """Fold a Job event stream into its final response."""
    terminal: ResultEvent | None = None
    async for event in events:
        if isinstance(event, ResultEvent):
            terminal = event
    if terminal is None:
        return JobResponse(answer="Stream produced no terminal result", success=False)
    return terminal.response()
