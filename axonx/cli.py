"""Command-line entry points for local Tasks and the resident application."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Sequence

from .application import Application
from .components.client import HttpClient
from .components.service import HttpService
from .config import resolve_app_config
from .constants import (
    AXONX_TASK_WORKSPACE_DIR,
    CLI_LOCAL_COMMANDS,
    CLI_RAW_ARGUMENTS,
    CLI_USAGE,
)
from .schema import ApplicationConfig, ClientOptions, Command
from .task.executor import TaskCatalog, TaskCommandExecutor
from .utils import load_env, print_logo
from .utils.cli import (
    parse_command,
    print_json,
)


def _run_server(command: Command) -> int:
    environment = load_env()
    arguments = {
        key: value
        for key, value in command.arguments.items()
        if key != CLI_RAW_ARGUMENTS
    }
    config = resolve_app_config(**arguments)
    config["environment"] = {**environment, **config.get("environment", {})}
    app = Application(**config)
    spec = app.app_config.service
    if spec and spec.backend != "http":
        raise ValueError("Only the http service is supported")
    service = HttpService(**(spec.model_dump() if spec else {}))
    if app.app_config.enable_logo:
        print_logo(app.app_config, service)
    service.run_app(app)
    return 0


def _run_remote_job(command: Command, client_options: ClientOptions) -> int:
    async def run():
        async with HttpClient(**client_options.model_dump()) as client:
            return await client.run_job(command.action, **command.arguments)

    response = asyncio.run(run())
    print(response.model_dump_json(indent=2))
    return 0 if response.success else 1


def _run_exec(command: Command) -> int:
    load_env(override=False)
    workspace_dir = os.environ.get(AXONX_TASK_WORKSPACE_DIR)
    if workspace_dir is None:
        app_config = ApplicationConfig.model_validate(
            resolve_app_config(log_config=False)
        )
        workspace_dir = app_config.workspace_dir
    result = TaskCommandExecutor(workspace_dir).execute(command)
    if isinstance(result, TaskCatalog):
        for name, task_class in sorted(result.tasks.items()):
            print(f"{name}\t{task_class.__module__}.{task_class.__name__}")
        return 0
    print_json(result.output)
    return result.exit_code


def _run_plugin(command: Command) -> int:
    from .plugin.cli import plugin_cli

    return plugin_cli(command.arguments.get(CLI_RAW_ARGUMENTS, ()))


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
        command, client_options = parse_command(args)
        handler = _LOCAL_HANDLERS.get(command.action)
        if handler is not None:
            return handler(command)
        return _run_remote_job(command, client_options)
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return (
            2
            if isinstance(exc, (FileNotFoundError, KeyError, TypeError, ValueError))
            else 1
        )


if __name__ == "__main__":
    raise SystemExit(main())
