"""Public Job stream events, including Agent messages and Task observations."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from ..task.models.events import LogEvent, ProgressEvent
from .models import JobResponse

AgentBlockType = Literal["thinking", "text", "tool", "system", "error"]


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


class ArtifactEvent(BaseModel):
    kind: Literal["artifact"] = "artifact"
    path: str
    sha256: str = ""
    size: int = 0
    media_type: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ResultEvent(JobResponse):
    kind: Literal["result"] = "result"

    @classmethod
    def from_response(cls, response: JobResponse) -> ResultEvent:
        return cls(**dict(response))

    def response(self) -> JobResponse:
        return JobResponse(**dict(self))


type JobEvent = Annotated[
    ProgressEvent | LogEvent | ArtifactEvent | AgentMessageEvent | ResultEvent,
    Field(discriminator="kind"),
]
JOB_EVENT_ADAPTER: TypeAdapter[JobEvent] = TypeAdapter(JobEvent)
