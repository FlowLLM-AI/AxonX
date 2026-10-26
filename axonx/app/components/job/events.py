"""Fold an execution event stream into its final Job response."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import aclosing

from ....client import events as client_events
from ....client import models


async def fold_events(events: AsyncIterator[client_events.JobEvent]) -> models.JobResponse:
    """Fold a Job event stream into its final response."""
    async with aclosing(events) as stream:
        async for event in stream:
            if isinstance(event, client_events.ResultEvent):
                return event.response()
    return models.JobResponse(answer="Stream produced no terminal result", success=False)
