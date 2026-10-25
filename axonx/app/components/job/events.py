"""Canonical streaming events emitted by Jobs."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from ..agent.events import AgentMessageEvent
from .models import JobResponse
from ....common.logs import LogEvent
from ....task.events import ProgressEvent


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
    async with aclosing(events) as stream:
        async for event in stream:
            if isinstance(event, ResultEvent):
                return event.response()
    return JobResponse(answer="Stream produced no terminal result", success=False)
