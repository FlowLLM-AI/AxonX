"""Backend-neutral persistence contract for Agent session transcripts."""

from __future__ import annotations

from typing import Any, NotRequired, Protocol, Required, TypedDict


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


class AgentSessionStore(Protocol):
    """Store opaque transcript entries without interpreting backend fields."""

    async def append(
        self, key: AgentSessionKey, entries: list[AgentSessionEntry]
    ) -> None: ...

    async def load(
        self, key: AgentSessionKey
    ) -> list[AgentSessionEntry] | None: ...

    async def list_sessions(self, project_key: str) -> list[AgentSessionListEntry]: ...

    async def load_summary(
        self, key: AgentSessionListKey
    ) -> AgentSessionSummary | None: ...

    async def save_summary(
        self, key: AgentSessionListKey, summary: AgentSessionSummary
    ) -> AgentSessionSummary: ...

    async def list_summaries(self, project_key: str) -> list[AgentSessionSummary]: ...

    async def delete(self, key: AgentSessionKey) -> None: ...

    async def list_subkeys(self, key: AgentSessionListKey) -> list[str]: ...


def json_entry(value: Any) -> AgentSessionEntry:
    """Narrow one already validated JSON object for static callers."""
    if not isinstance(value, dict) or not isinstance(value.get("type"), str):
        raise ValueError("Session entries must be JSON objects with a string type")
    return value
