"""Invoke public Jobs through a short-lived remote client."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import aclosing
from typing import Any

from ..job.events import JobEvent
from ..job.models import JobResponse
from .http import HttpClient


async def run_remote_job(
    name: str,
    arguments: Mapping[str, Any],
    **client_options,
) -> JobResponse:
    """Invoke one Job through a freshly connected HTTP client."""
    async with HttpClient(**client_options) as client:
        return await client.run_job(name, arguments)


async def stream_remote_job(
    name: str,
    arguments: Mapping[str, Any],
    **client_options,
) -> AsyncIterator[JobEvent]:
    """Stream one Job through a freshly connected HTTP client."""
    async with HttpClient(**client_options) as client:
        async with aclosing(client.stream_job(name, arguments)) as events:
            async for event in events:
                yield event
