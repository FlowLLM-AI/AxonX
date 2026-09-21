"""Adapt the AxonX AgentSessionStore to the Claude SDK contract."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import cast

from ..session_store import (
    AgentSessionEntry,
    AgentSessionKey,
    AgentSessionListKey,
    AgentSessionStore,
    AgentSessionSummary,
)


class ClaudeSessionStoreAdapter:
    def __init__(self, store: AgentSessionStore) -> None:
        self.store = store
        self._locks: defaultdict[tuple[str, str], asyncio.Lock] = defaultdict(
            asyncio.Lock
        )

    async def append(self, key, entries) -> None:
        from claude_agent_sdk import fold_session_summary

        agent_key = cast(AgentSessionKey, key)
        agent_entries = cast(list[AgentSessionEntry], entries)
        lock_key = (agent_key["project_key"], agent_key["session_id"])
        async with self._locks[lock_key]:
            await self.store.append(agent_key, agent_entries)
            if agent_key.get("subpath") is None:
                summary_key = cast(AgentSessionListKey, agent_key)
                previous = await self.store.load_summary(summary_key)
                summary = fold_session_summary(previous, key, entries)
                await self.store.save_summary(
                    summary_key, cast(AgentSessionSummary, summary)
                )

    async def load(self, key):
        return await self.store.load(cast(AgentSessionKey, key))

    async def list_sessions(self, project_key: str):
        return await self.store.list_sessions(project_key)

    async def list_session_summaries(self, project_key: str):
        return await self.store.list_summaries(project_key)

    async def delete(self, key) -> None:
        await self.store.delete(cast(AgentSessionKey, key))

    async def list_subkeys(self, key):
        return await self.store.list_subkeys(cast(AgentSessionListKey, key))
