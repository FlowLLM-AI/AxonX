"""Adapt local service, Task and plugin operations to CLI inputs and output."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from ..utils.env import load_env
from .parser import ClientOptions, Command, parse_plugin_arguments, validate_cron_command
from .rendering import print_json

if TYPE_CHECKING:
    from ..task.runtime.settings import ExecutionSettings


def _execution_config(arguments: dict, options: ClientOptions) -> ExecutionSettings:
    from ..client import http as client
    from ..client.base import RemoteConnectionError, RemoteServiceError
    from ..task.runtime.settings import ExecutionSettings
    from ..utils.logging import LoggingConfig, configure_logging

    load_env(override=False)
    try:
        response = asyncio.run(client.run_remote_job("get_config", {}, **options.connection()))
    except RemoteConnectionError:
        values = {}
        print("Service unavailable; using CLI execution options and built-in defaults", file=sys.stderr)
    else:
        if (
            not response.success
            or not isinstance(response.answer, dict)
            or not ExecutionSettings.model_fields.keys() <= response.answer.keys()
        ):
            raise RemoteServiceError("Service returned an invalid or failed get_config result")
        values = dict(response.answer)
    overrides = {key: arguments.pop(key) for key in ExecutionSettings.model_fields if key in arguments}
    if "environment" in overrides:
        overrides["environment"] = {**values.get("environment", {}), **overrides["environment"]}
    config = ExecutionSettings.model_validate({**values, **overrides})
    os.environ.update(config.environment)
    configure_logging(
        LoggingConfig(
            log_dir=config.log_dir,
            timezone=config.timezone,
            log_to_console=config.log_to_console,
            log_to_file=config.log_to_file,
        )
    )
    return config


def _run_app(command: Command, _options: ClientOptions) -> int:
    from ..daemon.launcher import start

    return start(
        command.arguments,
        command_prefix=(sys.executable, "-m", "axonx.cli"),
        startup_arguments=(command.action, *command.raw_arguments),
        validate_command=validate_cron_command,
    )


def _run_exec(command: Command, options: ClientOptions) -> int:
    from ..plugin.discovery import discover_task_registrations
    from ..task.runtime.catalog import TaskCatalog
    from ..task.runtime.executor import TaskExecutor

    if not command.arguments:
        load_env(override=False)
        for name, task_class in TaskCatalog(registrations=discover_task_registrations()).tasks().items():
            print(f"{name}\t{task_class.__module__}.{task_class.__name__}")
        return 0
    inputs = dict(command.arguments)
    try:
        name = inputs.pop("task")
    except KeyError:
        raise ValueError("Missing required option: --task") from None
    config = _execution_config(inputs, options)
    catalog = TaskCatalog(registrations=discover_task_registrations())
    if isinstance(inputs.get("upstream_task_ids"), str):
        upstream_ids = inputs["upstream_task_ids"]
        inputs["upstream_task_ids"] = [item.strip() for item in upstream_ids.split(",")] if upstream_ids.strip() else []
    task = catalog.resolve(name)(
        inputs,
        workspace_path=config.workspace_dir,
        reg_name=name,
        timezone=config.timezone,
        execution_target=config.execution_target,
    )
    status = TaskExecutor(resolve_task=catalog.resolve).execute(task)
    print_json(status.output_params)
    return status.exit_code


def _run_kill(command: Command, options: ClientOptions) -> int:
    from ..task.runtime.lifecycle import kill_task

    arguments = dict(command.arguments)
    if "task_id" not in arguments:
        raise ValueError("Missing required option: --task-id")
    config = _execution_config(arguments, options)
    print_json(kill_task(Path(config.workspace_dir).expanduser().resolve(), **arguments))
    return 0


def _run_plugin(command: Command, _options: ClientOptions) -> int:
    from ..plugin.discovery import get_installed_plugin, list_installed_plugins
    from ..plugin.installer import install_plugin, prepare_artifact, uninstall_plugin

    try:
        args = parse_plugin_arguments(command.raw_arguments)
    except SystemExit as exc:
        return exc.code
    load_env(override=False)
    if args.command == "list":
        result = list_installed_plugins()
    elif args.command == "show":
        result = get_installed_plugin(args.plugin)
    elif args.command == "inspect" and not Path(args.plugin).expanduser().exists():
        result = get_installed_plugin(args.plugin)
    elif args.command in {"inspect", "build"}:
        result = prepare_artifact(args.plugin, output=args.output)
    elif args.command == "install":
        source = Path(args.plugin).expanduser().resolve() if args.editable else None
        if source is not None and not source.is_dir():
            raise ValueError(f"Editable plugin path must be a project directory: {source}")
        result = install_plugin(prepare_artifact(args.plugin, output=args.output), editable_source=source)
    else:
        result = uninstall_plugin(args.plugin)
    print_json(result)
    return 0


LOCAL_HANDLERS = {
    "app": _run_app,
    "exec": _run_exec,
    "kill": _run_kill,
    "plugin": _run_plugin,
}
