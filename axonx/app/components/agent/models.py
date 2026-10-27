"""Agent message blocks and session models."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, Required, TypedDict

from pydantic import BaseModel, Field

from ....client.events import AgentBlockType

AGENT_DEPTH_ARGUMENT = "agent_depth"


class AgentSessionInfo(BaseModel):
    session_id: str
    summary: str
    last_modified: float
    file_size: int | None = None
    custom_title: str | None = None
    first_prompt: str | None = None
    git_branch: str | None = None
    cwd: str | None = None
    tag: str | None = None
    created_at: float | None = None
    backend: str


class AgentHistoryBlock(BaseModel):
    block_id: str
    block_type: AgentBlockType
    message_uuid: str
    role: Literal["user", "assistant", "system"]
    status: str
    text: str
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentSession(BaseModel):
    info: AgentSessionInfo
    blocks: list[AgentHistoryBlock]


class AgentMutationResult(BaseModel):
    session_id: str


class AgentSessionKey(TypedDict):
    project_key: str
    session_id: str
    subpath: NotRequired[str]


class AgentSessionListKey(TypedDict):
    project_key: str
    session_id: str


class AgentSessionEntry(TypedDict, total=False):
    type: Required[str]
    uuid: str
    timestamp: str
    # Backend-owned JSON fields are intentionally allowed.


class AgentSessionListEntry(TypedDict):
    session_id: str
    mtime: int


class AgentSessionSummary(TypedDict):
    session_id: str
    mtime: int
    data: dict[str, Any]
