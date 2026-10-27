"""Expose Jobs as JSON responses, event streams, and MCP tools."""

import json
from collections.abc import AsyncIterator
from contextlib import aclosing
from functools import partial
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException
from fastmcp import FastMCP
from fastmcp.tools import FunctionTool
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import StreamingResponse

from .....client import http as client
from .....client.config import (
    PROTOCOL_ROUTE_HEALTH,
    PROTOCOL_ROUTE_JOB,
    PROTOCOL_ROUTE_JOB_EVENTS,
    PROTOCOL_ROUTE_JOBS,
    PROTOCOL_SSE_DATA_PREFIX,
    PROTOCOL_SSE_EVENT_PREFIX,
    PROTOCOL_SSE_MEDIA_TYPE,
)
from .....client.events import JobEvent, ResultEvent
from .....client.models import JobCatalog, JobResponse

if TYPE_CHECKING:
    from ....core.application import Application


class JobInvocation(BaseModel):
    """Separate business arguments from HTTP transport targeting."""

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


class JobRoutes(APIRouter):
    """Share one public Job catalog across JSON, SSE, and MCP transports."""

    def __init__(self, app: "Application", *, authenticated: bool) -> None:
        super().__init__()
        self.app = app
        self.public_jobs = {
            name: job for name, job in app.context.jobs.items() if job.is_public(authenticated=authenticated)
        }
        self.add_api_route(PROTOCOL_ROUTE_HEALTH, self.health, methods=["GET"], response_model=JobResponse)
        self.add_api_route(PROTOCOL_ROUTE_JOBS, self.list_jobs, methods=["GET"], response_model=JobResponse)
        self.add_api_route(PROTOCOL_ROUTE_JOB, self.run_job, methods=["POST"], response_model=JobResponse)
        self.add_api_route(PROTOCOL_ROUTE_JOB_EVENTS, self.stream_job, methods=["POST"])

    async def health(self) -> JobResponse:
        return JobResponse(answer={"running": self.app.is_started})

    async def list_jobs(self, target: str | None = None) -> JobResponse:
        if target is None:
            items = [job.info for job in self.public_jobs.values()]
        else:
            try:
                configured = self.app.app_config.resolve_target(target)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            async with client.HttpClient(target=configured.address, token=configured.token) as remote:
                items = await remote.list_jobs()
        return JobResponse(answer=JobCatalog(items=items, total=len(items)))

    async def run_job(self, name: str, invocation: JobInvocation) -> JobResponse:
        return await self._invoke(name, invocation, streaming=False)

    async def stream_job(self, name: str, invocation: JobInvocation) -> StreamingResponse:
        """Stream one job's events as Server-Sent Events."""
        return await self._invoke(name, invocation, streaming=True)

    async def _invoke(self, name: str, invocation: JobInvocation, *, streaming: bool):
        job = self.public_jobs.get(name)
        if invocation.target is None and (job is None or (streaming and not job.enable_stream)):
            raise HTTPException(404, "Unknown job")
        try:
            if streaming:
                # Validate before sending headers; later failures become terminal events.
                events = self.app.stream_job(name, arguments=invocation.arguments, target=invocation.target)
                return StreamingResponse(_event_stream(events), media_type=PROTOCOL_SSE_MEDIA_TYPE)
            return await self.app.run_job(
                name,
                arguments=invocation.arguments,
                target=invocation.target,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    def create_mcp_server(self) -> FastMCP:
        """Expose exactly the same public Jobs as the HTTP catalog."""
        server = FastMCP(name=self.app.app_config.app_name)
        response_schema = JobResponse.model_json_schema()
        for job in self.public_jobs.values():
            server.add_tool(
                FunctionTool(
                    name=job.name,
                    description=job.description,
                    parameters=job.parameters,
                    output_schema=response_schema,
                    fn=partial(self._run_tool, job.name),
                    return_type=JobResponse,
                ),
            )
        return server

    async def _run_tool(self, name: str, /, **arguments: Any) -> JobResponse:
        return await self.app.run_job(name, arguments=arguments)
