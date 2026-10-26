"""Assemble one application service supervised by the standalone daemon."""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from ..app.async_work import run_blocking
from ..app.components.cron.parser import load_crontab
from ..app.config.resolver import resolve_app_config
from ..app.core.banner import print_logo
from ..common.env import load_env
from ..task.runtime.settings import ExecutionSettings
from . import client as daemon
from .update import UpdateClient
from .update_worker import versions

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
    cron = arguments.pop("cron", None)
    config = resolve_app_config(**arguments)
    config["environment"] = {**environment, **config.get("environment", {})}
    settings = ExecutionSettings.model_validate(config)
    from ..app.config.models import ApplicationConfig

    app_config = ApplicationConfig.model_validate(config)
    if app_config.service is None:
        raise ValueError("Application configuration does not define a service")
    cwd = Path.cwd().resolve()
    service = app_config.service.model_dump()
    directory = daemon.runtime_directory(
        app_config.workspace_dir, service.get("host", "0.0.0.0"), service.get("port", 1024), cwd
    )
    if os.environ.get(daemon.SOCKET):
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
        ready_to_launch = asyncio.Event()

        async def launch(entry):
            await ready_to_launch.wait()
            await run_blocking(
                lambda: daemon.request(
                    "exec",
                    command=[*command_prefix, *entry.command[1:]],
                    cwd=str(cwd),
                    environment=settings.execution_environment(),
                    log_file=str(Path(settings.log_dir).expanduser().resolve() / "cron" / f"line-{entry.line}.log"),
                )
            )

        if cron is not None:
            config.setdefault("components", {})["cron"] = {
                "default": {"backend": "cron", "source": cron, "launch": launch, "validate_command": validate_command}
            }
        app = Application(updates=UpdateClient(directory, cwd, VERIFICATION), **config)

        async def ready():
            await run_blocking(
                lambda: daemon.request(
                    "ready",
                    stop_timeout=app.context.service.cleanup_timeout + 1,
                    versions=versions(),
                )
            )
            ready_to_launch.set()

        app.context.service.on_ready = ready
        service = app.context.service
        if app.app_config.enable_logo:
            print_logo(app.app_config, service)
        service.run_app(app)
        return 0
    if cron is not None:
        load_crontab(cron, validate_command)
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
