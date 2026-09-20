"""Coalescing subscriptions for Task workspace changes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TaskChanges:
    """One coalesced batch of Task workspace changes."""

    task_ids: frozenset[str] = field(default_factory=frozenset)
    resync: bool = False


class TaskChangeSubscription(AsyncIterator[TaskChanges]):
    """A non-blocking mailbox owned by one repository consumer."""

    def __init__(self, on_close: Callable[[TaskChangeSubscription], None]) -> None:
        self._on_close = on_close
        self._task_ids: set[str] = set()
        self._resync = False
        self._ready = asyncio.Event()
        self._closed = False

    def publish(self, changes: TaskChanges) -> None:
        if self._closed:
            return
        self._task_ids.update(changes.task_ids)
        self._resync |= changes.resync
        self._ready.set()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._on_close(self)
        self._ready.set()

    def __aiter__(self) -> TaskChangeSubscription:
        return self

    async def __anext__(self) -> TaskChanges:
        await self._ready.wait()
        if self._closed:
            raise StopAsyncIteration
        changes = TaskChanges(frozenset(self._task_ids), self._resync)
        self._task_ids.clear()
        self._resync = False
        self._ready.clear()
        return changes
