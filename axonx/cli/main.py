"""Command-line orchestration for local Tasks and the resident application."""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Sequence

from ..components.client import ClientOptions
from ..components.job import ResultEvent
from ..config import ApplicationConfig, resolve_app_config
from ..constants import (
    AXONX_TASK_LOG_DIR,
    AXONX_TASK_TIMEZONE,
    AXONX_TASK_WORKSPACE_DIR,
    CLI_EXEC_COMMAND,
    CLI_HELP_COMMAND,
    CLI_LOCAL_COMMANDS,
    CLI_PLUGIN_COMMAND,
    CLI_RAW_ARGUMENTS,
    CLI_START_COMMAND,
    CLI_USAGE,
    REMOTE_IP_ARGUMENT,
)
from ..core import Application, run_remote_job, stream_remote_job
from ..plugin_kit.verification import verify_remote_submission
from ..task.runtime import TaskCatalog, TaskCommandExecutor
from ..utils import LoggingConfig, configure_logging, load_env
from .parser import Command, parse_command
from .rendering import print_event_blocks, print_json, print_logo


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
    service = app.context.service
    if service is None:
        raise ValueError("Application configuration does not define a service")
    if app.app_config.enable_logo:
        print_logo(app.app_config, service)
    service.run_app(app)
    return 0


def _run_remote_job(command: Command, client_options: ClientOptions) -> int:
    load_env(override=False)
    options = client_options.model_dump(exclude={"stream", "stream_format"})
    if options["token"] is None:
        options["token"] = os.environ.get("AXONX_SERVICE_TOKEN") or None
    arguments = dict(command.arguments)
    arguments.pop(CLI_RAW_ARGUMENTS, None)
    target_ip = arguments.pop(REMOTE_IP_ARGUMENT, None)

    if client_options.stream:

        async def stream() -> bool:
            success = False
            async for event in stream_remote_job(
                command.action,
                arguments,
                target_ip=target_ip,
                preflight=verify_remote_submission,
                **options,
            ):
                if client_options.stream_format == "json":
                    print(event.model_dump_json(), flush=True)
                else:
                    print_event_blocks(event)
                if isinstance(event, ResultEvent):
                    success = event.success
            return success

        return 0 if asyncio.run(stream()) else 1

    async def run():
        return await run_remote_job(
            command.action,
            arguments,
            target_ip=target_ip,
            preflight=verify_remote_submission,
            **options,
        )

    response = asyncio.run(run())
    print(response.model_dump_json(indent=2))
    return 0 if response.success else 1


def _run_exec(command: Command) -> int:
    load_env(override=False)
    workspace_dir = os.environ.get(AXONX_TASK_WORKSPACE_DIR)
    log_dir = os.environ.get(AXONX_TASK_LOG_DIR)
    timezone = os.environ.get(AXONX_TASK_TIMEZONE)
    if workspace_dir is None or log_dir is None or timezone is None:
        app_config = ApplicationConfig.model_validate(
            resolve_app_config(log_config=False)
        )
        workspace_dir = workspace_dir or app_config.workspace_dir
        log_dir = log_dir or app_config.log_dir
        timezone = timezone or app_config.timezone
    configure_logging(LoggingConfig(log_dir=log_dir))
    result = TaskCommandExecutor(workspace_dir, timezone=timezone).execute(command)
    if isinstance(result, TaskCatalog):
        for name, task_class in sorted(result.tasks.items()):
            print(f"{name}\t{task_class.__module__}.{task_class.__name__}")
        return 0
    print_json(result.output)
    return result.exit_code


def _run_plugin(command: Command, client_options: ClientOptions | None = None) -> int:
    from ..plugin_kit.cli import plugin_cli

    return plugin_cli(command.arguments.get(CLI_RAW_ARGUMENTS, ()), client_options)


def _show_help(_command: Command) -> int:
    print(CLI_USAGE)
    return 0


_LOCAL_HANDLERS = {
    CLI_EXEC_COMMAND: _run_exec,
    CLI_HELP_COMMAND: _show_help,
    CLI_PLUGIN_COMMAND: _run_plugin,
    CLI_START_COMMAND: _run_server,
}

assert _LOCAL_HANDLERS.keys() == CLI_LOCAL_COMMANDS


def main(argv: Sequence[str] | None = None) -> int:
    """Run one AxonX command and return its process exit status."""
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        command, client_options = parse_command(args)
        if command.action == CLI_PLUGIN_COMMAND:
            return _run_plugin(command, client_options)
        handler = _LOCAL_HANDLERS.get(command.action)
        if handler is not None:
            return handler(command)
        return _run_remote_job(command, client_options)
    except Exception as exc:  # noqa: BLE001 - CLI boundary converts failures to exit codes.
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return (
            2
            if isinstance(exc, (FileNotFoundError, KeyError, TypeError, ValueError))
            else 1
        )


__all__ = ["main"]
