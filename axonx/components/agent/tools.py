"""Expose AxonX Jobs to an agent as in-process MCP tools.

A tool call goes through the application's shared job dispatcher, so what the
model invokes gets the same argument validation, logging, and remote routing an
external caller gets — and what comes back is one Job's answer rendered as text
the model can read.
"""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter

from ...constants import AGENT_DEPTH_ARGUMENT, REMOTE_IP_ARGUMENT
from ..job.contracts import JobResponse

if TYPE_CHECKING:
    from ...core.context import ApplicationContext
    from ...core.dispatch import JobDispatcher
    from ..job.base import BaseJob

_ANSWER_ADAPTER = TypeAdapter(Any)

_SERVER_NAME = "axonx"


class JobToolServer:
    """The Jobs one agent may call, presented as a single MCP server.

    Resolved once, when the agent starts, and attached to every turn's options:
    which Jobs an agent may call is configuration, while how deep the current
    turn sits in a call chain is a property of the turn itself.
    """

    def __init__(self, jobs: Sequence["BaseJob"], dispatcher: "JobDispatcher") -> None:
        self._jobs = tuple(jobs)
        self._dispatcher = dispatcher

    @classmethod
    def resolve(
        cls,
        names: Sequence[str],
        app_context: "ApplicationContext | None",
    ) -> "JobToolServer | None":
        """Return the server for one component's configured Job names, if any.

        Rejects at startup rather than at the first tool call: a name an operator
        mistyped is a configuration error, not something to discover mid-turn.
        """
        if not names:
            return None
        if app_context is None:
            raise RuntimeError("job_tools require an application context")
        if any(not isinstance(name, str) or not name for name in names):
            raise ValueError("job_tools must contain non-empty Job names")
        if len(names) != len(set(names)):
            raise ValueError("job_tools must not contain duplicate names")
        jobs = []
        for name in names:
            job = app_context.jobs.get(name)
            if job is None:
                raise KeyError(f"Job {name!r} is not configured")
            jobs.append(job)
        return cls(jobs, app_context.dispatcher)

    def attach(self, options: dict, depth: int) -> None:
        """Add this server, and permission for its tools, to one options mapping."""
        from claude_agent_sdk import create_sdk_mcp_server

        servers = options.get("mcp_servers") or {}
        if not isinstance(servers, dict):
            raise ValueError("job_tools require mcp_servers to be a mapping")
        if _SERVER_NAME in servers:
            raise ValueError(
                f"mcp_servers already contains the reserved name {_SERVER_NAME!r}",
            )
        options["mcp_servers"] = {
            **servers,
            _SERVER_NAME: create_sdk_mcp_server(
                name=_SERVER_NAME,
                tools=[_job_tool(job, self._dispatcher, depth) for job in self._jobs],
            ),
        }
        allowed = options.get("allowed_tools") or []
        if not isinstance(allowed, list):
            raise ValueError("job_tools require allowed_tools to be a list")
        options["allowed_tools"] = list(
            dict.fromkeys(
                [*allowed, *(f"mcp__{_SERVER_NAME}__{job.name}" for job in self._jobs)],
            ),
        )


def _job_tool(job: "BaseJob", dispatcher: "JobDispatcher", depth: int) -> Any:
    """Wrap one AxonX Job as an SDK MCP tool.

    A Job that declares the recursion counter is handed the depth this call sits
    at, so a Job that runs an agent of its own can refuse to descend further. The
    counter stays out of the schema the model sees, and is filled back in here —
    which is the only reason a tool call needs to know about it at all.
    """
    from claude_agent_sdk import SdkMcpTool

    nested = AGENT_DEPTH_ARGUMENT in job.injected_parameters
    supports_target = job.is_remotely_invocable and not job.injected_parameters

    async def call(arguments: dict[str, Any]) -> dict[str, Any]:
        payload = dict(arguments)
        remote_ip = payload.pop(REMOTE_IP_ARGUMENT, None) if supports_target else None
        system = {AGENT_DEPTH_ARGUMENT: depth + 1} if nested else None
        response = await dispatcher.run(
            job.name,
            payload,
            system=system,
            remote_ip=remote_ip,
        )
        return {
            "content": [{"type": "text", "text": _render_answer(response)}],
            "is_error": not response.success,
        }

    return SdkMcpTool(
        name=job.name,
        description=job.description,
        input_schema=_tool_input_schema(job),
        handler=call,
    )


def _tool_input_schema(job: "BaseJob") -> dict:
    """Add agent-surface transport targeting without mutating the Job schema."""
    schema = deepcopy(job.parameters)
    if job.is_remotely_invocable and not job.injected_parameters:
        schema.setdefault("properties", {})[REMOTE_IP_ARGUMENT] = {
            "type": "string",
            "description": "Optional IP of a configured remote AxonX node.",
        }
    return schema


def _render_answer(response: JobResponse) -> str:
    """Render one Job answer as the text the model reads.

    A Job answers with a payload model as often as with a string, and ``str()``
    on one is a Python repr: nested entries arrive as ``WorkspaceEntry(...)``
    rather than as the fields they hold. The HTTP and MCP routes serialize those
    same models as JSON, and this is that rendering.
    """
    answer = response.answer
    if isinstance(answer, str):
        return answer
    return _ANSWER_ADAPTER.dump_json(answer).decode()
