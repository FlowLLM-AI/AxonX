"""Expose Jobs as JSON responses, event streams, and MCP tools."""

import json
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Any

from fastapi import APIRouter, HTTPException
from fastmcp import FastMCP
from fastmcp.tools import FunctionTool
from starlette.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ....constants import (
    PROTOCOL_ROUTE_HEALTH,
    PROTOCOL_ROUTE_JOB,
    PROTOCOL_ROUTE_JOB_EVENTS,
    PROTOCOL_ROUTE_JOBS,
    PROTOCOL_SSE_DATA_PREFIX,
    PROTOCOL_SSE_EVENT_PREFIX,
    PROTOCOL_SSE_MEDIA_TYPE,
)
from ...client.http import HttpClient
from ...job.contracts import JobCatalog, JobResponse
from ...job.events import JobEvent, ResultEvent


class JobInvocation(BaseModel):
    """HTTP-only envelope separating Job arguments from transport targeting."""

    model_config = ConfigDict(extra="forbid")
    arguments: dict[str, Any] = Field(default_factory=dict)
    target: str | None = None


def _event_frame(event: JobEvent) -> str:
    """Encode one typed event as a single Server-Sent Event."""
    payload = json.dumps(event.model_dump(mode="json"), ensure_ascii=False, default=str)
    return f"{PROTOCOL_SSE_EVENT_PREFIX}{event.kind}\n{PROTOCOL_SSE_DATA_PREFIX}{payload}\n\n"


async def _event_stream(events: AsyncIterator[JobEvent]) -> AsyncIterator[str]:
    """Render events through the first terminal ResultEvent, then close their source."""
    try:
        async with aclosing(events) as stream:
            async for event in stream:
                yield _event_frame(event)
                if isinstance(event, ResultEvent):
                    return
    except Exception as exc:
        yield _event_frame(ResultEvent.from_response(JobResponse().fail(exc)))
        return
    yield _event_frame(ResultEvent(answer="Stream produced no terminal result", success=False))


def create_jobs_router(app, public_jobs) -> APIRouter:
    """Expose the job catalog, the folded job route, and the streaming route."""
    router = APIRouter()

    @router.get(PROTOCOL_ROUTE_HEALTH, response_model=JobResponse)
    async def health():
        return JobResponse(answer={"running": app.is_started})

    @router.get(PROTOCOL_ROUTE_JOBS, response_model=JobResponse)
    async def list_jobs(target: str | None = None):
        if target is None:
            items = [job.info for job in public_jobs.values()]
        else:
            try:
                configured = app.app_config.resolve_target(target)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            async with HttpClient(target=configured.address, token=configured.token) as client:
                items = await client.list_jobs()
        return JobResponse(answer=JobCatalog(items=items, total=len(items)))

    @router.post(PROTOCOL_ROUTE_JOB, response_model=JobResponse)
    async def run_job(name: str, invocation: JobInvocation):
        if invocation.target is None and name not in public_jobs:
            raise HTTPException(404, "Unknown job")
        try:
            return await app.run_job(
                name,
                arguments=invocation.arguments,
                target=invocation.target,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post(PROTOCOL_ROUTE_JOB_EVENTS)
    async def stream_job(name: str, invocation: JobInvocation):
        """Stream one job's events as Server-Sent Events."""
        job = public_jobs.get(name)
        if invocation.target is None and (job is None or not job.is_streamable):
            raise HTTPException(404, "Unknown job")
        try:
            # Validate local Jobs and target configuration before starting the body.
            # Remote execution failures become terminal events in _event_stream.
            events = app.stream_job(
                name,
                arguments=invocation.arguments,
                target=invocation.target,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return StreamingResponse(_event_stream(events), media_type=PROTOCOL_SSE_MEDIA_TYPE)

    return router


def create_mcp_server(app, public_jobs) -> FastMCP:
    """Mirror the ordinary JSON Job surface through Streamable HTTP MCP."""
    server = FastMCP(name=app.app_config.app_name)
    for job in public_jobs.values():

        def make_tool(job_name):
            async def execute_tool(**arguments) -> JobResponse:
                return await app.run_job(job_name, arguments=arguments)

            return execute_tool

        server.add_tool(
            FunctionTool(
                name=job.name,
                description=job.description,
                parameters=job.parameters,
                output_schema=JobResponse.model_json_schema(),
                fn=make_tool(job.name),
                return_type=JobResponse,
            ),
        )
    return server
