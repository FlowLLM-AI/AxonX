"""Command-line entry points for local Tasks and the resident application."""

from __future__ import annotations

import asyncio
import sys
from typing import Any, Sequence

from .application import Application
from .components.client import HttpClient
from .components import HttpService, R
from .config import resolve_app_config
from .constants import CLI_LOCAL_COMMANDS, CLI_USAGE
from .enumeration import ComponentEnum
from .schema import Command, HttpClientOptions
from .task import BaseTask
from .utils.cli_utils import (
    CommandParser,
    pop_required_string,
    print_json,
)


def _installed_tasks() -> dict[str, type[BaseTask]]:
    """Return built-in Tasks; configured plugin Tasks run through TaskManager."""
    return R.get_all(ComponentEnum.TASK)


def _run_server(command: Command) -> int:
    app = Application(**resolve_app_config(**command.arguments))
    spec = app.config.service
    if spec and spec.backend != "http":
        raise ValueError("Only the http service is supported")
    HttpService(**(spec.model_dump() if spec else {})).run_app(app)
    return 0


def _run_remote_job(
    action: str,
    arguments: dict[str, Any],
    client_options: HttpClientOptions,
) -> int:
    async def run():
        async with HttpClient(**client_options.model_dump()) as client:
            return await client.run_job(action, **arguments)

    response = asyncio.run(run())
    print(response.model_dump_json(indent=2))
    return 0 if response.success else 1


def _run_exec(command: Command) -> int:
    tasks = _installed_tasks()
    if not command.arguments:
        for name, task_class in sorted(tasks.items()):
            print(f"{name}\t{task_class.__module__}.{task_class.__name__}")
        return 0

    name, config = pop_required_string(command.arguments, "task")
    task_class = tasks.get(name)
    if task_class is None:
        available = ", ".join(sorted(tasks)) or "none"
        raise ValueError(f"Unknown Task: {name}. Available: {available}")

    task = task_class(config)
    task.execute()
    print_json(task.output)
    return task.status.exit_code


def _run_plugin(command: Command) -> int:
    from .plugin.cli import plugin_cli

    return plugin_cli(command.passthrough)


def _show_help(_command: Command) -> int:
    print(CLI_USAGE)
    return 0


_LOCAL_HANDLERS = {
    "exec": _run_exec,
    "help": _show_help,
    "plugin": _run_plugin,
    "start": _run_server,
}

assert _LOCAL_HANDLERS.keys() == CLI_LOCAL_COMMANDS


def main(argv: Sequence[str] | None = None) -> int:
    """Run one AxonX command and return its process exit status."""
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        command = CommandParser(args).parse()
        handler = _LOCAL_HANDLERS.get(command.action)
        if handler is not None:
            return handler(command)
        return _run_remote_job(command.action, command.arguments, command.client)
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
