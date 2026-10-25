"""Command-line orchestration for local Tasks and the resident application."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from .options import ClientOptions
from .parser import Command, parse_command
from .rendering import print_event_blocks, print_json, print_logo
from .usage import CLI_USAGE
from ..common.config import ConfigLoader
from ..common.connection import AXONX_CLI_REQUEST_ID
from ..common.constants import CONFIG_ENTRY_POINT_GROUP
from ..common.env import load_env
from ..common.logging import LoggingConfig, configure_logging
from ..common.logs import LogEvent
from ..common.runtime import (
    AXONX_TASK_LOG_DIR,
    AXONX_TASK_TIMEZONE,
    AXONX_TASK_WORKSPACE_DIR,
    RuntimeSettings,
)
from ..common.workspace import Workspace
from ..daemon import client as daemon

if TYPE_CHECKING:
    from ..cron.scheduler import CronScheduler

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
    arguments = dict(command.arguments)
    config = ConfigLoader(
        Path(__file__).resolve().parents[1] / "app" / "config", group=CONFIG_ENTRY_POINT_GROUP
    ).resolve(**arguments)
    config["environment"] = {**environment, **config.get("environment", {})}
    role = os.environ.get(daemon.ROLE)
    if role == "cron":
        asyncio.run(_run_cron(config["cron"], RuntimeSettings.model_validate(config)))
        return 0
    from ..app.config.models import ApplicationConfig

    app_config = ApplicationConfig.model_validate(config)
    if role == "service":
        from ..app.core.application import Application

        app = Application(**config)
        service = app.context.service
        if app.app_config.enable_logo:
            print_logo(app.app_config, service)
        service.run_app(app)
        return 0
    if role is not None:
        raise ValueError(f"Unknown daemon worker role: {role}")
    if app_config.service is None:
        raise ValueError("Application configuration does not define a service")
    if app_config.cron is not None:
        _cron(app_config.cron, app_config)  # Validate the complete file before replacing this launcher.
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


def _cron(source: str, config: RuntimeSettings) -> CronScheduler:
    from ..cron.scheduler import CronScheduler

    return CronScheduler(
        source,
        workspace_dir=config.workspace_dir,
        log_dir=config.log_dir,
        timezone=config.timezone,
        environment=config.environment,
        launch=lambda entry: daemon.request("exec", arguments=list(entry.arguments), line=entry.line),
    )


async def _run_cron(source: str, config: RuntimeSettings) -> None:
    scheduler = _cron(source, config)
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
    from ..app.components.client.remote import run_remote_job, stream_remote_job
    from ..app.components.job.events import ResultEvent

    client_options = _load_client_options(client_options)
    options = client_options.model_dump(exclude={"stream", "stream_format"})
    arguments = dict(command.arguments)
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


def _execution_config() -> RuntimeSettings:
    load_env(override=False)
    values = {
        name: os.environ[key]
        for name, key in {
            "workspace_dir": AXONX_TASK_WORKSPACE_DIR,
            "log_dir": AXONX_TASK_LOG_DIR,
            "timezone": AXONX_TASK_TIMEZONE,
        }.items()
        if key in os.environ
    }
    if "workspace_dir" not in values and "AXONX_WORKSPACE_DIR" in os.environ:
        values["workspace_dir"] = os.environ["AXONX_WORKSPACE_DIR"]
    config = RuntimeSettings(**values)
    configure_logging(LoggingConfig(log_dir=config.log_dir, timezone=config.timezone))
    return config


def _run_kill(command: Command) -> int:
    from ..task.storage.records import kill_task

    arguments = dict(command.arguments)
    config = _execution_config()
    workspace_dir = arguments.pop("workspace_dir", config.workspace_dir)
    status = kill_task(Workspace(workspace_dir).root, **arguments)
    print_json(status.model_dump(mode="json"))
    return 0


def _run_task_catalog(command: Command) -> int:
    load_env(override=False)
    from ..task.catalog.resolver import (
        get_task_definition,
        list_installed_task_definitions,
    )

    if command.action == "get_task_definition":
        if set(command.arguments) != {"task"}:
            raise ValueError("Expected --task NAME")
        result = get_task_definition(command.arguments["task"])
    else:
        result = list_installed_task_definitions(**command.arguments)
    print_json(
        [item.model_dump(mode="json") for item in result]
        if isinstance(result, list)
        else result.model_dump(mode="json")
    )
    return 0


def _run_exec(command: Command) -> int:
    from ..task.catalog.resolver import installed_tasks
    from ..task.runtime.executor import TaskExecutor

    config = _execution_config()
    workspace_dir, timezone = config.workspace_dir, config.timezone
    if not command.arguments:
        for name, task_class in sorted(installed_tasks().items()):
            print(f"{name}\t{task_class.__module__}.{task_class.__name__}")
        return 0
    inputs = dict(command.arguments)
    try:
        name = inputs.pop("task")
    except KeyError:
        raise ValueError("Missing required option: --task") from None
    status = TaskExecutor(workspace_dir, timezone=timezone).execute(name, inputs)
    print_json(status.output_params)
    return status.exit_code


def _run_plugin(command: Command) -> int:
    from .plugin import plugin_cli

    load_env(override=False)
    return plugin_cli(command.raw_arguments)


def _run_remote_cli(command: Command, options: ClientOptions) -> int:
    from ..app.components.client.remote import stream_remote_job
    from ..app.components.job.events import ResultEvent

    options = _load_client_options(options)
    argv = [command.action, *command.raw_arguments]
    if command.action not in _LOCAL_HANDLERS:
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
    "exec": _run_exec,
    "kill": _run_kill,
    "list_installed_task_definitions": _run_task_catalog,
    "get_task_definition": _run_task_catalog,
    "plugin": _run_plugin,
    "start": _run_server,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Run one AxonX command and return its process exit status."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(CLI_USAGE)
        return 0
    try:
        command, client_options = parse_command(args)
        if os.environ.get(AXONX_CLI_REQUEST_ID) and (
            command.action in {"start", "cli"} or client_options.target is not None
        ):
            raise ValueError("Remote CLI cannot start a service or forward to another target")
        if client_options.target is not None:
            return _run_remote_cli(command, client_options)
        if command.action == "start":
            return _run_server(command, args)
        handler = _LOCAL_HANDLERS.get(command.action)
        if handler is not None:
            return handler(command)
        return _run_remote_job(command, client_options)
    except Exception as exc:  # noqa: BLE001 - CLI boundary converts failures to exit codes.
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2 if isinstance(exc, (FileNotFoundError, KeyError, TypeError, ValueError)) else 1
