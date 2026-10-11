"""Service-owned update admission, durable status and process handoff."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ...enums import ComponentEnum
from ...plugin_kit.environment import environment_operation, run_in_thread
from ..base import BaseComponent
from ..registry import provider
from .worker import check_protected_paths, save, versions

# Each HTTP/MCP request owns its shutdown callbacks, including child Job tasks.
RESPONSE_CALLBACKS: ContextVar[list | None] = ContextVar("update_response_callbacks", default=None)
VERIFICATION = (
    "from axonx.cli import main; from axonx_studio import static_dir; "
    "assert (static_dir() / 'index.html').is_file(), 'Studio assets are missing'"
)


@provider("local")
class UpdateManager(BaseComponent):
    """Accept one update and run it only after application resources have closed."""

    component_type = ComponentEnum.UPDATER

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pending: Path | None = None

    @property
    def directory(self) -> Path:
        """Keep update state under the protected runtime workspace."""
        return self.workspace_path.resolve() / "updates"

    async def _start(self) -> None:
        from .worker import RECORD_ENV

        current = os.environ.get(RECORD_ENV)
        for path in self.directory.glob("*/record.json"):
            if str(path) == current:
                continue
            record = json.loads(path.read_text(encoding="utf-8"))
            if record["phase"] not in {"succeeded", "failed"}:
                record.update(phase="failed", error="Update interrupted before service startup")
                save(path, record)

    @environment_operation
    async def request(self, mode: str, force: bool = False) -> dict:
        """Preflight before entering maintenance; return an acceptance record."""
        service = self.app_context.service
        callbacks = RESPONSE_CALLBACKS.get()
        if (
            callbacks is None
            or not getattr(service, "restart_arguments", None)
            or getattr(service, "server", None) is None
        ):
            raise RuntimeError("Self-update requires a resident service started with axonx start")
        if self.pending is not None:
            raise RuntimeError("An update is already pending")
        plan = await run_in_thread(self._plan, mode, service)
        for manager in self.app_context.components.get("task_manager", {}).values():
            active = [status for status in await manager.list_statuses() if not status.state.is_terminal]
            if active and not force:
                raise RuntimeError("Active Tasks prevent updating; force=true cancels managed Runs")
            for status in active:
                if not await manager.cancel(task_id=status.task_id, run_id=status.run_id):
                    # Completion may race with cancellation; recheck before rejecting.
                    if not (await manager.get_status(status.task_id)).state.is_terminal:
                        raise RuntimeError(f"Cannot stop active Run: {status.run_id}")
        update_id = uuid4().hex
        folder = self.directory / update_id
        folder.mkdir(parents=True, mode=0o700)
        path = folder / "record.json"
        record = {
            "update_id": update_id,
            "mode": mode,
            "phase": "accepted",
            "error": None,
            "created_at": datetime.now(UTC).isoformat(),
            "before": versions(),
            "after": None,
            "commit": None,
        }
        (folder / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        shutil.copyfile(Path(__file__).with_name("worker.py"), folder / "worker.py")
        save(path, record)
        self.pending = path
        self.app_context.metadata["maintenance"] = True
        callbacks.append(service.request_shutdown)
        return record

    def _plan(self, mode: str, service) -> dict:
        if mode not in {"git", "pip", "restart"}:
            raise ValueError("Unknown update mode")
        cwd = service.startup_directory
        plan = {"cwd": str(cwd), "arguments": service.restart_arguments}
        if mode == "restart":
            return plan
        plan["verification"] = VERIFICATION
        source_file = Path(__file__).resolve().parents[2] / "__init__.py"
        if mode == "pip":
            if Path(source_file).resolve().parent == (cwd / "axonx").resolve():
                raise ValueError("Startup directory shadows the installed package; use Git update or start elsewhere")
            from importlib import metadata
            from importlib.util import find_spec

            for name in ("axonx", "axonx-studio"):
                spec = find_spec(name.replace("-", "_"))
                module_file = source_file if name == "axonx" else (spec.origin if spec else None)
                try:
                    distribution = metadata.distribution(name)
                except metadata.PackageNotFoundError:
                    if module_file is not None:
                        raise ValueError(f"Uninstalled source package shadows {name}; use Git update") from None
                    continue
                direct = distribution.read_text("direct_url.json")
                if not distribution.read_text("WHEEL") or (
                    direct and json.loads(direct).get("dir_info", {}).get("editable")
                ):
                    raise ValueError("Source installations require Git update")
                installed = distribution.locate_file(name.replace("-", "_") + "/__init__.py")
                if module_file and Path(module_file).resolve() != Path(installed).resolve():
                    raise ValueError(f"Source imports shadow installed {name}; use Git update")
            return plan
        if not shutil.which("git") or not shutil.which("npm"):
            raise ValueError("Git update requires git and npm")
        repository = Path(
            subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=cwd,
                text=True,
            ).strip()
        ).resolve()
        if not Path(source_file).resolve().is_relative_to(repository / "axonx"):
            raise ValueError("The running AxonX package does not belong to the startup repository")
        if not (repository / "axonx_studio" / "package.json").is_file():
            raise ValueError("The startup repository does not contain AxonX Studio")
        protected = [
            Path(os.path.abspath(self.workspace_path)),
            self.workspace_path.resolve(),
            Path(os.path.abspath(Path(self.app_config.log_dir).expanduser())),
            Path(self.app_config.log_dir).expanduser().resolve(),
            Path(os.path.abspath(sys.prefix)),
            Path(sys.prefix).resolve(),
            Path(sys.executable).absolute(),
        ]
        tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=repository, text=True, timeout=10)
        committed = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", "-z", "HEAD"],
            cwd=repository,
            text=True,
            timeout=10,
        )
        paths = set()
        for item in protected:
            if item == repository:
                raise ValueError("Runtime and Python directories must be separate from the repository root")
            if item.is_relative_to(repository):
                paths.add(item.relative_to(repository).parts[0])
        for item in service.configuration_paths:
            if item.is_relative_to(repository):
                relative = item.relative_to(repository).as_posix()
                # Tracked configuration is source; local configuration must survive cleaning.
                if relative not in {*tracked.split("\0"), *committed.split("\0")}:
                    paths.add(relative)
        if service.environment_file is not None and service.environment_file.is_relative_to(repository):
            paths.add(service.environment_file.relative_to(repository).as_posix())
        protected_paths = sorted(paths)
        check_protected_paths(tracked, protected_paths)
        check_protected_paths(committed, protected_paths)
        excludes = []
        for path in protected_paths:
            pattern = "".join("\\" + char if char in "\\*?[]" else char for char in path)
            excludes.extend(["-e", "/" + pattern])
        plan.update(repository=str(repository), protected=protected_paths, excludes=excludes)
        return plan

    def status(self, update_id: str | None = None) -> dict:
        """Read one update or the latest record, plus a bounded log tail."""
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

    def fail(self, error: str) -> None:
        """Settle a handoff that could not complete normal shutdown."""
        if self.pending is not None:
            record = json.loads(self.pending.read_text(encoding="utf-8"))
            record.update(phase="failed", error=error)
            save(self.pending, record)

    def handoff(self) -> None:
        """Replace the closed service with its snapshotted, independent updater."""
        if self.pending is not None:
            try:
                os.execv(sys.executable, [sys.executable, str(self.pending.with_name("worker.py")), str(self.pending)])
            except OSError as exc:
                self.fail(f"Updater handoff failed: {exc}")
                raise
