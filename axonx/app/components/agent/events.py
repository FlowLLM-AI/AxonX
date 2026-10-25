"""Domain execution and shared operations."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .models import AgentBlockType


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
