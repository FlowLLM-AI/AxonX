"""Validate startup, snapshot the daemon and assemble its application service."""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
import shutil
import socket
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from ..app.config.models import ApplicationConfig
from ..app.config.resolver import resolve_app_config
from ..app.core.banner import print_logo
from ..app.crontabs import load_crontab
from ..client.config import AXONX_SERVICE_TARGET, normalize_target
from ..task.runtime.settings import ExecutionSettings
from ..utils.async_work import run_blocking
from ..utils.env import load_env
from .client import SOCKET, DaemonClient

VERIFICATION = (
    "from axonx.app.core.application import Application; from axonx_studio import static_dir; "
    "assert (static_dir() / 'index.html').is_file(), 'Studio assets are missing'"
)


def runtime_directory(workspace: str, host: str, port: int, cwd: Path) -> Path:
    """Identify one service by workspace, machine, address and startup directory."""
    identity = f"{socket.gethostname()}:{host}:{port}:{cwd}"
    key = hashlib.sha256(identity.encode()).hexdigest()[:16]
    return Path(workspace).expanduser().resolve() / "daemon" / key


def _launch(plan: dict, directory: Path) -> None:
    """Hold the service lock across exec into a standard-library-only snapshot."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "daemon.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"AxonX is already running: {directory}") from exc
        digest = hashlib.sha256(str(directory).encode()).hexdigest()[:16]
        plan = {
            **plan,
            "directory": str(directory),
            "socket": str(Path(tempfile.gettempdir()) / f"axonx-{os.getuid()}-{digest}.sock"),
        }
        path = directory / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        for name in ("supervisor.py", "update.py"):
            shutil.copyfile(Path(__file__).with_name(name), directory / name)
        os.set_inheritable(lock.fileno(), True)
        os.execve(
            plan["python"],
            [plan["python"], "-S", str(directory / "supervisor.py"), str(path), str(lock.fileno())],
            plan["environment"],
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
    config["execution_target"] = settings.execution_target
    app_config = ApplicationConfig.model_validate(config)
    if app_config.service is None:
        raise ValueError("Application configuration does not define a service")
    cwd = Path.cwd().resolve()
    service = app_config.service.model_dump()
    directory = runtime_directory(
        app_config.workspace_dir, service.get("host", "0.0.0.0"), service.get("port", 1024), cwd
    )
    if os.environ.get(SOCKET):
        from ..app.core.application import Application

        daemon = DaemonClient(directory, cwd, VERIFICATION)
        environment = dict(settings.environment)
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
            host = "127.0.0.1" if service.host == "0.0.0.0" else service.host
            host = f"[{host}]" if ":" in host else host
            await run_blocking(
                daemon.launch,
                [*command_prefix, *entry.command[1:]],
                {
                    **os.environ,
                    **environment,
                    AXONX_SERVICE_TARGET: normalize_target(f"{host}:{service.port}"),
                    "AXONX_SERVICE_TOKEN": service.token or "",
                },
                Path(settings.log_dir).expanduser().resolve() / "cron" / f"line-{entry.line}.log",
            )

        if cron is not None:
            config.setdefault("components", {})["cron"] = {
                "default": {"backend": "cron", "source": cron, "launch": launch, "validate_command": validate_command}
            }
        app = Application(updates=daemon, **config)

        async def ready():
            await run_blocking(daemon.ready, app.context.service.cleanup_timeout + 1)
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
    _launch(plan, directory)
    return 0
