"""HTTP update admission and read-only status for the process daemon."""

import json
import os
import shutil
import subprocess
from contextvars import ContextVar
from functools import partial
from pathlib import Path

from ...daemon import client as daemon
from ...enums import ComponentEnum
from ...utils.async_work import run_blocking
from ..base import BaseComponent
from ..registry import provider
from .worker import versions

# Nested CLI requests share their outer HTTP response's completion boundary.
RESPONSE_CALLBACKS: ContextVar[list | None] = ContextVar("update_response_callbacks", default=None)
VERIFICATION = (
    "from axonx.cli import main; from axonx_studio import static_dir; "
    "assert (static_dir() / 'index.html').is_file(), 'Studio assets are missing'"
)


@provider("local")
class UpdateManager(BaseComponent):
    """Delegate process ownership to the daemon; never stop the service directly."""

    component_type = ComponentEnum.UPDATER

    @property
    def directory(self) -> Path:
        if value := os.environ.get(daemon.DIRECTORY):
            return Path(value) / "updates"
        service = self.app_context.service
        return (
            daemon.runtime_directory(
                self.app_config.workspace_dir, service.host, service.port, service.startup_directory
            )
            / "updates"
        )

    async def request(self, mode: str) -> dict:
        callbacks = RESPONSE_CALLBACKS.get()
        if callbacks is None or not os.environ.get(daemon.SOCKET):
            raise RuntimeError("Self-update requires a daemon started with axonx start")
        if self.app_context.metadata.get("maintenance"):
            raise RuntimeError("An update is already pending")
        self.app_context.metadata["maintenance"] = True
        try:
            plan = await run_blocking(self._plan, mode, self.app_context.service)
            record = await run_blocking(
                partial(
                    daemon.request,
                    "prepare_update",
                    mode=mode,
                    plan=plan,
                    worker=str(Path(__file__).with_name("worker.py")),
                    versions=versions(),
                )
            )
            callbacks.append(partial(daemon.request, "commit_update", update_id=record["update_id"]))
            return record
        except BaseException:
            self.app_context.metadata.pop("maintenance", None)
            raise

    def _plan(self, mode: str, service) -> dict:
        if mode not in {"git", "pip", "restart"}:
            raise ValueError("Unknown update mode")
        cwd = service.startup_directory
        plan = {"cwd": str(cwd), "verification": VERIFICATION}
        if mode == "restart":
            return plan
        source = Path(__file__).resolve().parents[2]
        if mode == "pip":
            from importlib import metadata
            from importlib.util import find_spec

            for name in ("axonx", "axonx-studio"):
                specification = find_spec(name.replace("-", "_"))
                try:
                    distribution = metadata.distribution(name)
                except metadata.PackageNotFoundError:
                    if specification is not None:
                        raise ValueError(f"Uninstalled source shadows {name}; use Git update") from None
                    continue
                direct = distribution.read_text("direct_url.json")
                if not distribution.read_text("WHEEL") or (
                    direct and json.loads(direct).get("dir_info", {}).get("editable")
                ):
                    raise ValueError("Source installations require Git update")
                installed = distribution.locate_file(name.replace("-", "_") + "/__init__.py")
                if specification and Path(specification.origin).resolve() != Path(installed).resolve():
                    raise ValueError(f"Source imports shadow installed {name}; use Git update")
            if source == (cwd / "axonx").resolve():
                raise ValueError("Startup directory shadows installed AxonX; use Git update")
            return plan
        if not shutil.which("git") or not shutil.which("npm"):
            raise ValueError("Git update requires git and npm")
        repository = Path(
            subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=cwd, text=True, timeout=10).strip()
        ).resolve()
        if not source.is_relative_to(repository / "axonx"):
            raise ValueError("The running AxonX package does not belong to the startup repository")
        if not (repository / "axonx_studio" / "package.json").is_file():
            raise ValueError("The startup repository does not contain AxonX Studio")
        plan["repository"] = str(repository)
        return plan

    def status(self, update_id: str | None = None) -> dict:
        if update_id is None:
            paths = sorted(self.directory.glob("*/record.json"), key=lambda item: item.stat().st_mtime_ns)
            if not paths:
                return {"record": None, "log": ""}
            path = paths[-1]
        else:
            if len(update_id) != 32 or any(char not in "0123456789abcdef" for char in update_id):
                raise ValueError("Invalid update_id")
            path = self.directory / update_id / "record.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        log_path = path.with_name("update.log")
        log = ""
        if log_path.exists():
            with log_path.open("rb") as stream:
                stream.seek(max(0, log_path.stat().st_size - 65536))
                log = stream.read(65536).decode("utf-8", errors="replace")
        return {"record": record, "log": log}
