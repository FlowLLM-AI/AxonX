"""Invoke service Jobs or forward raw CLI arguments to an explicit target."""

from __future__ import annotations

import sys
from contextlib import aclosing

from ..client import http as client
from ..client.events import ResultEvent
from ..task.models.events import LogEvent
from ..utils.env import load_env
from .commands import LOCAL_HANDLERS
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


async def run_remote(command: Command, options: ClientOptions) -> int:
    """Load connection credentials once and select the remote operation."""
    load_env(override=False)
    connection = options.connection()
    if command.action in LOCAL_HANDLERS:
        return await _forward_cli(command, options, connection)
    return await _run_job(command, options, connection)


async def _run_job(command: Command, options: ClientOptions, connection: dict) -> int:
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


async def _forward_cli(command: Command, options: ClientOptions, connection: dict) -> int:
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
