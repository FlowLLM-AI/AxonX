"""Parse commands, route public APIs and render their results."""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from ..app.connection import AXONX_CLI_REQUEST_ID
from ..task.models.events import LogEvent
from ..task.runtime.settings import ExecutionSettings
from ..utils.env import load_env
from ..utils.logging import LoggingConfig, configure_logging
from .options import ClientOptions
from .parser import Command, parse_command, validate_cron_command
from .rendering import print_event_blocks, print_json
from .usage import CLI_USAGE

# Defaults affect CLI queries only; callers can explicitly request complete records.
_QUERY_DEFAULTS = {
    "status": {"detail": "summary"},
    "wait_task": {"detail": "summary"},
    "preview_file": {"limit": 20, "max_bytes": 8192},
    "list_agent_sessions": {"limit": 20},
    "get_agent_session": {"limit": 20},
    "list_installed_task_definitions": {"include_schemas": False},
}


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


def _execution_config() -> ExecutionSettings:
    load_env(override=False)
    config = ExecutionSettings.from_environment()
    configure_logging(LoggingConfig(log_dir=config.log_dir, timezone=config.timezone))
    return config


def _run_kill(command: Command) -> int:
    from ..task.runtime.lifecycle import kill_task

    arguments = dict(command.arguments)
    config = _execution_config()
    workspace_dir = arguments.pop("workspace_dir", config.workspace_dir)
    status = kill_task(Path(workspace_dir).expanduser().resolve(), **arguments)
    print_json(status.model_dump(mode="json"))
    return 0


def _run_task_catalog(command: Command) -> int:
    load_env(override=False)
    from ..plugin.catalog import get_task_definition, list_installed_task_definitions

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
    from ..plugin.catalog import installed_tasks, resolve_task
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
    status = TaskExecutor(
        workspace_dir, timezone=timezone, execution_target=config.execution_target, resolve_task=resolve_task
    ).execute(name, inputs)
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
            from ..daemon.launcher import start

            return start(
                command.arguments,
                command_prefix=(sys.executable, "-m", "axonx.cli"),
                startup_arguments=args,
                validate_command=validate_cron_command,
            )
        handler = _LOCAL_HANDLERS.get(command.action)
        if handler is not None:
            return handler(command)
        return _run_remote_job(command, client_options)
    except Exception as exc:  # noqa: BLE001 - CLI boundary converts failures to exit codes.
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2 if isinstance(exc, (FileNotFoundError, KeyError, TypeError, ValueError)) else 1
