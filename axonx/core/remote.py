"""Transport public Jobs to a remote AxonX node."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Any

from ..components.client import BaseClient, HttpClient
from ..components.job.base import JobEvent, JobResponse

type RemotePreflight = Callable[
    [BaseClient, str, Mapping[str, Any]], Awaitable[None]
]


async def run_remote_job(
    name: str,
    arguments: Mapping[str, Any],
    *,
    target_ip: str | None = None,
    preflight: RemotePreflight | None = None,
    **client_options,
) -> JobResponse:
    """Invoke one Job through a freshly connected HTTP client."""
    async with HttpClient(**client_options) as client:
        if preflight is not None:
            await preflight(client, name, arguments)
        return await client.run_job(name, arguments, remote_ip=target_ip)


async def stream_remote_job(
    name: str,
    arguments: Mapping[str, Any],
    *,
    target_ip: str | None = None,
    preflight: RemotePreflight | None = None,
    **client_options,
) -> AsyncIterator[JobEvent]:
    """Stream one Job through a freshly connected HTTP client."""
    async with HttpClient(**client_options) as client:
        if preflight is not None:
            await preflight(client, name, arguments)
        async for event in client.stream_job(name, arguments, remote_ip=target_ip):
            yield event
