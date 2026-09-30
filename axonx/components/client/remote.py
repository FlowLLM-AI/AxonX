"""Invoke public Jobs through a short-lived remote client."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any

from ..job.contracts import JobResponse
from ..job.events import JobEvent
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
        async for event in client.stream_job(name, arguments):
            yield event
