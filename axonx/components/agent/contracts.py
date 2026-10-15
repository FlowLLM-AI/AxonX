"""Backend-neutral Agent session presentation contracts."""

from typing import Any, Literal

from pydantic import BaseModel, Field

AgentBlockType = Literal["thinking", "text", "tool", "system", "error"]


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
