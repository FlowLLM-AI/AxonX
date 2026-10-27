"""Job result folding and invocation-scoped response-completion callbacks."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import aclosing
from contextvars import ContextVar

from ....client import events as client_events
from ....client import models

RESPONSE_CALLBACKS: ContextVar[list[Callable[[], None]] | None] = ContextVar("response_callbacks", default=None)


async def fold_events(events: AsyncIterator[client_events.JobEvent]) -> models.JobResponse:
    """Fold a Job event stream into its final response."""
    async with aclosing(events) as stream:
        async for event in stream:
            if isinstance(event, client_events.ResultEvent):
                return event.response()
    return models.JobResponse(answer="Stream produced no terminal result", success=False)
