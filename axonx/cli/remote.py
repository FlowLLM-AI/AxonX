"""Invoke service Jobs or forward raw CLI arguments to an explicit target."""

from __future__ import annotations

import sys
from contextlib import aclosing
from pathlib import Path

from ..client import http as client
from ..client.events import ResultEvent
from ..client.models import JobCatalog, JobResponse
from ..task.models.events import LogEvent
from .parser import ClientOptions, Command
from .rendering import print_event_blocks, print_json

# Defaults bound CLI query output; explicit arguments always take precedence.
_QUERY_DEFAULTS = {
    "status": {"detail": "summary"},
    "wait_task": {"detail": "summary"},
    "preview_file": {"limit": 20, "max_bytes": 8192},
    "list_agent_sessions": {"limit": 20},
    "get_agent_session": {"limit": 20},
}


async def run_http(command: Command, options: ClientOptions, connection: dict) -> int:
    """Adapt HTTP operations with the same connection and response conventions as Jobs."""
    if options.stream:
        raise ValueError(f"{command.action} does not support --stream")
    arguments = dict(command.arguments)
    if command.action in {"upload", "upload_archive", "discard_file"} and "path" not in arguments:
        raise ValueError("Missing required option: --path")
    response = JobResponse()
    async with client.HttpClient(**connection) as remote:
        if command.action in {"upload", "upload_archive"}:
            path = Path(arguments.pop("path")).expanduser()
            upload = remote.upload if command.action == "upload" else remote.upload_archive
            response.answer = await upload(path, **arguments)
        elif command.action == "discard_file":
            response.answer = {"path": await remote.discard_file(**arguments)}
        elif command.action == "health":
            response.success = await remote.health(**arguments)
            response.answer = {"running": response.success}
        else:
            items = await remote.list_jobs(**arguments)
            response.answer = JobCatalog(items=items, total=len(items))
    print_json(response, indent=2)
    return 0 if response.success else 1


async def run_job(command: Command, options: ClientOptions, connection: dict) -> int:
    """Call a configured Job and render its response or event stream."""
    arguments = {**_QUERY_DEFAULTS.get(command.action, {}), **command.arguments}
    if not options.stream:
        response = await client.run_remote_job(command.action, arguments, **connection)
        print_json(response, indent=2)
        return 0 if response.success else 1
    success = False
    async with aclosing(client.stream_remote_job(command.action, arguments, **connection)) as events:
        async for event in events:
            if options.stream_format == "json":
                print_json(event, flush=True)
            else:
                print_event_blocks(event)
            if isinstance(event, ResultEvent):
                success = event.success
    return 0 if success else 1


async def forward_cli(command: Command, options: ClientOptions, connection: dict) -> int:
    """Run a native command through the target service's cli Job."""
    argv = [command.action, *command.raw_arguments]
    if command.action in {"exec", "kill"}:
        argv.extend(["--client-timeout", str(options.timeout)])

    async with aclosing(client.stream_remote_job("cli", {"argv": argv}, **connection)) as events:
        async for event in events:
            if isinstance(event, LogEvent):
                output = sys.stderr if event.channel == "stderr" else sys.stdout
                print(event.content, end="", file=output, flush=True)
            elif isinstance(event, ResultEvent):
                code = event.answer.get("exit_code") if isinstance(event.answer, dict) else None
                if isinstance(code, int) and not isinstance(code, bool):
                    return code if code >= 0 else 128 - code
                print(event.answer, file=sys.stderr)
                return 1
    return 1
