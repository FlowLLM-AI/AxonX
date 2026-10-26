"""Daemon update planning and durable status."""

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import client as daemon
from . import update_worker
from .update_worker import versions


class UpdateClient:
    """Delegate process ownership to the daemon; never stop the service directly."""

    def __init__(self, directory: Path, startup_directory: Path, verification: str) -> None:
        self._directory = directory
        self.startup_directory = startup_directory
        self.verification = verification

    @property
    def directory(self) -> Path:
        if value := os.environ.get(daemon.DIRECTORY):
            return Path(value) / "updates"
        return self._directory / "updates"

    def prepare(self, mode: str) -> dict:
        if not os.environ.get(daemon.SOCKET):
            raise RuntimeError("Self-update requires a daemon started with axonx start")
        return daemon.request(
            "prepare_update",
            mode=mode,
            plan=self._plan(mode),
            worker=update_worker.__file__,
            versions=versions(),
        )

    @staticmethod
    def commit(update_id: str) -> None:
        daemon.request("commit_update", update_id=update_id)

    def _plan(self, mode: str) -> dict:
        if mode not in {"git", "pip", "restart"}:
            raise ValueError("Unknown update mode")
        cwd = self.startup_directory
        plan = {"cwd": str(cwd), "verification": self.verification}
        if mode == "restart":
            return plan
        source = Path(__file__).resolve().parents[1]
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
