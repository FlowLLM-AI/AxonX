"""Launch the application and Cron workers supervised by the standalone daemon."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, TYPE_CHECKING

from ..app.config.resolver import resolve_app_config
from ..app.core.banner import print_logo
from ..common.env import load_env
from ..task.runtime.settings import ExecutionSettings
from . import client as daemon
from .update import UpdateClient
from .update_worker import versions

if TYPE_CHECKING:
    from ..cron.scheduler import CronScheduler

VERIFICATION = (
    "from axonx.app.core.application import Application; from axonx_studio import static_dir; "
    "assert (static_dir() / 'index.html').is_file(), 'Studio assets are missing'"
)


def start(
    arguments: Mapping[str, Any],
    *,
    command_prefix: Sequence[str],
    startup_arguments: Sequence[str],
    validate_command: Callable[[Sequence[str]], None],
) -> int:
    inherited = dict(os.environ)
    environment = load_env()
    arguments = dict(arguments)
    config = resolve_app_config(**arguments)
    config["environment"] = {**environment, **config.get("environment", {})}
    settings = ExecutionSettings.model_validate(config)
    cron = config.pop("cron", None)
    role = os.environ.get(daemon.ROLE)
    if role == "cron":
        if cron is None:
            raise ValueError("A Cron worker requires --cron SOURCE")
        asyncio.run(_run_cron(cron, settings, command_prefix, validate_command))
        return 0
    from ..app.config.models import ApplicationConfig

    app_config = ApplicationConfig.model_validate(config)
    if role == "service":
        from ..app.core.application import Application

        environment = settings.task_environment()
        environment["PYTHONPATH"] = os.pathsep.join(
            filter(
                None,
                (str(Path(__file__).resolve().parents[2]), environment.get("PYTHONPATH", os.environ.get("PYTHONPATH"))),
            )
        )
        config["environment"] = environment
        config["command"] = (*command_prefix[:1], "-u", *command_prefix[1:])
        service_options = config.get("service") or {}
        directory = daemon.runtime_directory(
            settings.workspace_dir,
            service_options.get("host", "0.0.0.0"),
            service_options.get("port", 1024),
            Path.cwd(),
        )
        app = Application(updates=UpdateClient(directory, Path.cwd().resolve(), VERIFICATION), **config)
        if os.environ.get(daemon.SOCKET):

            async def ready():
                await asyncio.to_thread(
                    daemon.request,
                    "ready",
                    cron=cron is not None,
                    stop_timeout=app.context.service.cleanup_timeout + 1,
                    versions=versions(),
                )

            app.context.service.on_ready = ready
        service = app.context.service
        if app.app_config.enable_logo:
            print_logo(app.app_config, service)
        service.run_app(app)
        return 0
    if role is not None:
        raise ValueError(f"Unknown daemon worker role: {role}")
    if app_config.service is None:
        raise ValueError("Application configuration does not define a service")
    if cron is not None:
        _cron(cron, settings, command_prefix, validate_command)
    cwd = Path.cwd().resolve()
    service = app_config.service.model_dump()
    directory = daemon.runtime_directory(
        app_config.workspace_dir, service.get("host", "0.0.0.0"), service.get("port", 1024), cwd
    )
    plan = {
        "python": sys.executable,
        "cwd": str(cwd),
        "environment": inherited,
        "command": [*command_prefix, *startup_arguments],
        "stop_timeout": service.get("cleanup_timeout", 15) + 1,
    }
    print(f"Starting AxonX daemon; worker logs: {directory}", flush=True)
    daemon.launch(plan, directory)
    return 0


def _cron(
    source: str,
    config: ExecutionSettings,
    command_prefix: Sequence[str],
    validate_command: Callable[[Sequence[str]], None],
) -> CronScheduler:
    from ..cron.scheduler import CronScheduler

    scheduler = CronScheduler(
        source,
        timezone=config.timezone,
        launch=lambda entry: daemon.request("exec", command=[*command_prefix, *entry.command[1:]], line=entry.line),
    )
    for entry in scheduler.entries:
        try:
            validate_command(entry.command)
        except ValueError as exc:
            raise ValueError(f"{scheduler.path}:{entry.line}: {exc}") from exc
    return scheduler


async def _run_cron(
    source: str,
    config: ExecutionSettings,
    command_prefix: Sequence[str],
    validate_command: Callable[[Sequence[str]], None],
) -> None:
    scheduler = _cron(source, config, command_prefix, validate_command)
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
                "cwd": str(Path.cwd().resolve()),
                "environment": config.execution_environment(),
                "log_dir": str(Path(config.log_dir).expanduser().resolve()),
            },
        )
        await stop.wait()
    finally:
        await scheduler.close()
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(signum)
