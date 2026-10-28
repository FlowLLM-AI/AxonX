"""Stop the daemon selected by the same configuration as ``axonx app``."""

import fcntl
import json
import sys
from pathlib import Path

import psutil

from axonx.app.config.loader import ConfigLoader
from axonx.app.config.models import ApplicationConfig
from axonx.cli.parser import parse_command, validate_cron_command
from axonx.daemon.launcher import runtime_directory
from axonx.utils.env import load_env


def stop_daemon(directory: Path, timeout: float) -> None:
    """Verify the locked supervisor before signalling it; never select by port."""
    lock_path = directory / "daemon.lock"
    if not lock_path.exists():
        print(f"No AxonX daemon at {directory}")
        return
    with lock_path.open("r+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            print(f"No running AxonX daemon at {directory}")
            return
        state = json.loads((directory / "processes.json").read_text(encoding="utf-8"))
        process = psutil.Process(state["pid"])
        expected = [str(directory / "supervisor.py"), str(directory / "plan.json")]
        argv = process.cmdline()
        if len(argv) != 5 or argv[1:4] != ["-S", *expected]:
            raise RuntimeError("Daemon identity does not match the selected configuration; nothing was stopped")
        service = psutil.Process(state["service"]) if state.get("service") else None
        if service is not None and service.ppid() != process.pid:
            raise RuntimeError("Service is not owned by the selected daemon; nothing was stopped")
        print(f"Stopping AxonX daemon pid={process.pid}")
        process.terminate()
        process.wait(timeout=timeout)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if service is not None and service.is_running() and service.status() != psutil.STATUS_ZOMBIE:
            raise RuntimeError("The old service is still running; deployment stopped before changing source")


def main(argv: list[str] | None = None) -> None:
    """Resolve the deployment's application arguments before stopping its daemon."""
    command, client = parse_command(["app", *(sys.argv[1:] if argv is None else argv)])
    if client.model_fields_set:
        raise ValueError("Deployment accepts local application options only")
    load_env()
    config = ApplicationConfig.model_validate(ConfigLoader().resolve(**command.arguments))
    for entry in config.cron:
        validate_cron_command(entry.argv)
    if config.service is None:
        raise ValueError("Application configuration does not define a service")
    service = config.service.model_dump()
    directory = runtime_directory(
        config.workspace_dir,
        service.get("host") or config.bind_host,
        service.get("port", 1024),
        Path.cwd().resolve(),
    )
    stop_daemon(directory, service.get("cleanup_timeout", 15) + 10)


if __name__ == "__main__":
    main()
