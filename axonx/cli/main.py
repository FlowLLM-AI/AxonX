"""Command-line orchestration for local Tasks and the resident application."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path
from collections.abc import Sequence

from ..components.client import ClientOptions
from ..components.job import LogEvent, ResultEvent
from ..config import ApplicationConfig, ConfigResolver, resolve_app_config
from ..constants import (
    AXONX_TASK_LOG_DIR,
    AXONX_TASK_TIMEZONE,
    AXONX_TASK_WORKSPACE_DIR,
    CLI_EXEC_COMMAND,
    CLI_LOCAL_COMMANDS,
    CLI_PLUGIN_COMMAND,
    CLI_RAW_ARGUMENTS,
    CLI_START_COMMAND,
    CLI_USAGE,
)
from ..core import Application, run_remote_job, stream_remote_job
from ..task.runtime import TaskCatalog, TaskCommandExecutor
from ..utils import LoggingConfig, configure_logging, load_env
from ..cron import CronScheduler
from ..daemon import client as daemon
from .parser import Command, parse_command
from .rendering import print_event_blocks, print_json, print_logo

# Defaults affect CLI queries only; callers can explicitly request complete records.
_QUERY_DEFAULTS = {
    "status": {"detail": "summary"},
    "wait_task": {"detail": "summary"},
    "preview_file": {"limit": 20, "max_bytes": 8192},
    "list_agent_sessions": {"limit": 20},
    "get_agent_session": {"limit": 20},
    "list_installed_task_definitions": {"include_schemas": False},
}


def _run_server(command: Command, startup_arguments: list[str] | None = None) -> int:
    inherited = dict(os.environ)
    environment = load_env()
    arguments = {key: value for key, value in command.arguments.items() if key != CLI_RAW_ARGUMENTS}
    config = ConfigResolver().resolve(**arguments)
    config["environment"] = {**environment, **config.get("environment", {})}
    app_config = ApplicationConfig.model_validate(config)
    role = os.environ.get(daemon.ROLE)
    if role == "service":
        app = Application(**config)
        service = app.context.service
        if app.app_config.enable_logo:
            print_logo(app.app_config, service)
        service.run_app(app)
        return 0
    if role == "cron":
        asyncio.run(_run_cron(app_config))
        return 0
    if role is not None:
        raise ValueError(f"Unknown daemon worker role: {role}")
    if app_config.service is None:
        raise ValueError("Application configuration does not define a service")
    if app_config.cron is not None:
        _cron(app_config)  # Validate the complete file before replacing this launcher.
    cwd = Path.cwd().resolve()
    service = app_config.service.model_dump()
    directory = daemon.runtime_directory(
        app_config.workspace_dir, service.get("host", "0.0.0.0"), service.get("port", 1024), cwd
    )
    plan = {
        "python": sys.executable,
        "cwd": str(cwd),
        "environment": inherited,
        "command": [sys.executable, "-m", "axonx.cli", *(startup_arguments or ["start"])],
        "stop_timeout": service.get("cleanup_timeout", 15) + 1,
    }
    print(f"Starting AxonX daemon; worker logs: {directory}", flush=True)
    daemon.launch(plan, directory)
    return 0


def _cron(config: ApplicationConfig) -> CronScheduler:
    return CronScheduler(
        config.cron,
        workspace_dir=config.workspace_dir,
        log_dir=config.log_dir,
        timezone=config.timezone,
        environment=config.environment,
    )


async def _run_cron(config: ApplicationConfig) -> None:
    scheduler = _cron(config)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    try:
        await scheduler.start()
        await asyncio.to_thread(
            daemon.request,
            "ready",
            execution={
                "cwd": str(scheduler.cwd),
                "environment": scheduler.environment,
                "log_dir": scheduler.log_dir,
            },
        )
        await stop.wait()
    finally:
        await scheduler.close()
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(signum)


def _load_client_options(options: ClientOptions) -> ClientOptions:
    load_env(override=False)
    if options.token is None:
        key = "AXONX_TARGET_TOKEN" if options.target is not None else "AXONX_SERVICE_TOKEN"
        options = options.model_copy(update={"token": os.environ.get(key) or None})
    return options


def _run_remote_job(command: Command, client_options: ClientOptions) -> int:
    client_options = _load_client_options(client_options)
    options = client_options.model_dump(exclude={"stream", "stream_format"})
    arguments = dict(command.arguments)
    arguments.pop(CLI_RAW_ARGUMENTS, None)
    for key, value in _QUERY_DEFAULTS.get(command.action, {}).items():
        arguments.setdefault(key, value)

    if client_options.stream:

        async def stream() -> bool:
            success = False
            async for event in stream_remote_job(
                command.action,
                arguments,
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
            resolve_app_config(log_config=False),
        )
        workspace_dir = workspace_dir or app_config.workspace_dir
        log_dir = log_dir or app_config.log_dir
        timezone = timezone or app_config.timezone
    configure_logging(LoggingConfig(log_dir=log_dir, timezone=timezone))
    result = TaskCommandExecutor(workspace_dir, timezone=timezone).execute(command)
    if isinstance(result, TaskCatalog):
        for name, task_class in sorted(result.tasks.items()):
            print(f"{name}\t{task_class.__module__}.{task_class.__name__}")
        return 0
    print_json(result.output)
    return result.exit_code


def _run_plugin(command: Command) -> int:
    from ..plugin_kit.cli import plugin_cli

    load_env(override=False)
    return plugin_cli(command.arguments.get(CLI_RAW_ARGUMENTS, ()))


def _run_remote_cli(command: Command, options: ClientOptions) -> int:
    options = _load_client_options(options)
    argv = [command.action, *command.arguments[CLI_RAW_ARGUMENTS]]
    if command.action not in CLI_LOCAL_COMMANDS:
        argv.extend(["--client-timeout", str(options.timeout)])
        if options.stream:
            argv.extend(["--stream", "true", "--stream-format", options.stream_format])

    async def run() -> int:
        async for event in stream_remote_job(
            "cli", {"argv": argv}, **options.model_dump(exclude={"stream", "stream_format"})
        ):
            if isinstance(event, LogEvent):
                output = sys.stderr if event.channel == "stderr" else sys.stdout
                print(event.content, end="", file=output, flush=True)
            elif isinstance(event, ResultEvent):
                if isinstance(event.answer, dict) and "exit_code" in event.answer:
                    code = event.answer["exit_code"]
                    return code if code >= 0 else 128 - code
                print(event.answer, file=sys.stderr)
                return 1
        return 1

    return asyncio.run(run())


_LOCAL_HANDLERS = {
    CLI_EXEC_COMMAND: _run_exec,
    CLI_PLUGIN_COMMAND: _run_plugin,
    CLI_START_COMMAND: _run_server,
}

assert _LOCAL_HANDLERS.keys() == CLI_LOCAL_COMMANDS


def main(argv: Sequence[str] | None = None) -> int:
    """Run one AxonX command and return its process exit status."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(CLI_USAGE)
        return 0
    try:
        command, client_options = parse_command(args)
        if client_options.target is not None:
            return _run_remote_cli(command, client_options)
        if command.action == CLI_START_COMMAND:
            return _run_server(command, args)
        handler = _LOCAL_HANDLERS.get(command.action)
        if handler is not None:
            return handler(command)
        return _run_remote_job(command, client_options)
    except Exception as exc:  # noqa: BLE001 - CLI boundary converts failures to exit codes.
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2 if isinstance(exc, (FileNotFoundError, KeyError, TypeError, ValueError)) else 1


__all__ = ["main"]
