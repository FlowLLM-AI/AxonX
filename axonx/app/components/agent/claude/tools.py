"""Expose AxonX Jobs to Claude Code as in-process MCP tools."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter

from .....client.config import TARGET_ARGUMENT
from ..models import AGENT_DEPTH_ARGUMENT

if TYPE_CHECKING:
    from ....core.dispatch import JobDispatcher
    from ...job.base import BaseJob

_ANSWER_ADAPTER = TypeAdapter(Any)
_SERVER_NAME = "axonx"


class JobToolServer:
    """Adapt resolved Jobs to MCP schemas and dispatcher-backed handlers."""

    def __init__(self, jobs: Sequence[BaseJob], dispatcher: JobDispatcher) -> None:
        self._jobs = tuple(jobs)
        self._dispatcher = dispatcher

    def attach(self, options: dict[str, Any], depth: int) -> None:
        from claude_agent_sdk import create_sdk_mcp_server

        servers = options.get("mcp_servers") or {}
        if not isinstance(servers, Mapping):
            raise ValueError("job_tools require mcp_servers to be a mapping of server names to configurations")
        if _SERVER_NAME in servers:
            raise ValueError(f"mcp_servers contains reserved name {_SERVER_NAME!r}")
        options["mcp_servers"] = {
            **servers,
            _SERVER_NAME: create_sdk_mcp_server(
                name=_SERVER_NAME,
                tools=[self._tool(job, depth) for job in self._jobs],
            ),
        }
        options["allowed_tools"] = list(
            dict.fromkeys(
                [*(options.get("allowed_tools") or []), *(f"mcp__{_SERVER_NAME}__{job.name}" for job in self._jobs)]
            )
        )

    def _tool(self, job: BaseJob, depth: int) -> Any:
        from claude_agent_sdk import SdkMcpTool

        nested = AGENT_DEPTH_ARGUMENT in job.injected_parameters
        supports_target = not job.injected_parameters
        schema = dict(job.parameters)
        if supports_target:
            schema["properties"] = {
                **schema.get("properties", {}),
                TARGET_ARGUMENT: {
                    "type": "string",
                    "description": "Optional address of a configured AxonX target service.",
                },
            }

        async def call(arguments: dict[str, Any]) -> dict[str, Any]:
            payload = dict(arguments)
            target = payload.pop(TARGET_ARGUMENT, None) if supports_target else None
            system = {AGENT_DEPTH_ARGUMENT: depth + 1} if nested else None
            response = await self._dispatcher.run(job.name, payload, system=system, target=target)
            answer = response.answer
            text = answer if isinstance(answer, str) else _ANSWER_ADAPTER.dump_json(answer).decode()
            return {"content": [{"type": "text", "text": text}], "is_error": not response.success}

        return SdkMcpTool(name=job.name, description=job.description, input_schema=schema, handler=call)
