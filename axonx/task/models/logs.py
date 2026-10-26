"""Log content and byte cursor contract shared by queries and streams."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class LogChunk(BaseModel):
    content: str = ""
    start_offset: int = 0
    next_offset: int = 0
    file_size: int = 0
    has_more_before: bool = False
    has_more_after: bool = False
    reset: bool = False


class LogEvent(LogChunk):
    kind: Literal["log"] = "log"
    channel: str = "task"

    @classmethod
    def from_chunk(cls, chunk: Any) -> LogEvent:
        return cls.model_validate(chunk, from_attributes=True)
