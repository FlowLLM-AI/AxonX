"""Canonical streaming events emitted by Jobs."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from ..agent.contracts import AgentBlockType
from ...logs import LogChunk
from ...progress import TaskStepStatus
from .contracts import JobResponse


class ProgressEvent(TaskStepStatus):
    kind: Literal["progress"] = "progress"

    @classmethod
    def from_status(cls, status: Any) -> ProgressEvent:
        return cls.model_validate(status, from_attributes=True)


class LogEvent(LogChunk):
    kind: Literal["log"] = "log"
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
    block_type: AgentBlockType
    delta: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentMessageEvent(BaseModel):
    kind: Literal["agent_message"] = "agent_message"
    session_id: str = Field(min_length=1)
    type_name: str
    message_uuid: str
    role: Literal["user", "assistant", "system"]
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
