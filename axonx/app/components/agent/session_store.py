"""Backend-neutral persistence contract for Agent session transcripts."""

from __future__ import annotations

from typing import Protocol

from .models import (
    AgentSessionEntry,
    AgentSessionKey,
    AgentSessionListEntry,
    AgentSessionListKey,
    AgentSessionSummary,
)


class AgentSessionStore(Protocol):
    """Store opaque transcript entries without interpreting backend fields."""

    async def append(self, key: AgentSessionKey, entries: list[AgentSessionEntry]) -> None: ...

    async def exists(self, key: AgentSessionKey) -> bool: ...

    async def load(self, key: AgentSessionKey) -> list[AgentSessionEntry] | None: ...

    async def list_sessions(self, project_key: str) -> list[AgentSessionListEntry]: ...

    async def load_summary(self, key: AgentSessionListKey) -> AgentSessionSummary | None: ...

    async def save_summary(self, key: AgentSessionListKey, summary: AgentSessionSummary) -> AgentSessionSummary: ...

    async def list_summaries(self, project_key: str) -> list[AgentSessionSummary]: ...

    async def delete(self, key: AgentSessionKey) -> None: ...

    async def list_subkeys(self, key: AgentSessionListKey) -> list[str]: ...
