"""Authenticated daemon control, update planning and durable status reads."""

import json
import os
import shutil
import socket
import subprocess
from importlib import metadata
from importlib.util import find_spec
from pathlib import Path

from . import update

DIRECTORY = "AXONX_DAEMON_DIRECTORY"
SOCKET = "AXONX_DAEMON_SOCKET"
TOKEN = "AXONX_DAEMON_TOKEN"


class DaemonClient:
    """Control the owning daemon and supply the application's update backend."""

    def __init__(self, directory: Path, cwd: Path, verification: str) -> None:
        self.directory = Path(os.environ.get(DIRECTORY) or directory) / "updates"
        self.cwd = cwd
        self.verification = verification

    @staticmethod
    def request(action: str, **values):
        """Use one bounded JSON exchange; failed requests are never retried."""
        if not os.environ.get(SOCKET) or not os.environ.get(TOKEN):
            raise RuntimeError("This operation requires a daemon started with axonx app")
        message = {"action": action, **values, "token": os.environ[TOKEN]}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(5)
            connection.connect(os.environ[SOCKET])
            with connection.makefile("rwb") as stream:
                stream.write(json.dumps(message).encode() + b"\n")
                stream.flush()
                response = json.loads(stream.readline(1024 * 1024))
        if "error" in response:
            raise RuntimeError(response["error"])
        return response["answer"]

    def ready(self, stop_timeout: float) -> None:
        """Announce the current service's readiness and installed versions."""
        self.request("ready", stop_timeout=stop_timeout, versions=update.versions())

    def launch(self, command: list[str], environment: dict[str, str], log_file: Path) -> dict:
        """Ask the daemon to own a command independently of the service."""
        return self.request("exec", command=command, cwd=str(self.cwd), environment=environment, log_file=str(log_file))

    def prepare(self, mode: str) -> dict:
        """Validate an update and let the daemon snapshot its executor."""
        return self.request(
            "prepare_update", mode=mode, plan=self._plan(mode), worker=update.__file__, versions=update.versions()
        )

    def commit(self, update_id: str) -> None:
        """Stop the service only after its update response has been delivered."""
        self.request("commit_update", update_id=update_id)

    def _plan(self, mode: str) -> dict:
        if mode not in {"git", "pip", "restart"}:
            raise ValueError("Unknown update mode")
        plan = {"cwd": str(self.cwd), "verification": self.verification}
        if mode == "restart":
            return plan
        source = Path(__file__).resolve().parents[1]
        if mode == "pip":
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
            if source == (self.cwd / "axonx").resolve():
                raise ValueError("Startup directory shadows installed AxonX; use Git update")
            return plan
        if not shutil.which("git") or not shutil.which("npm"):
            raise ValueError("Git update requires git and npm")
        repository = Path(
            subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"], cwd=self.cwd, text=True, timeout=10
            ).strip()
        ).resolve()
        if not source.is_relative_to(repository / "axonx"):
            raise ValueError("The running AxonX package does not belong to the startup repository")
        if not (repository / "axonx_studio" / "package.json").is_file():
            raise ValueError("The startup repository does not contain AxonX Studio")
        plan["repository"] = str(repository)
        return plan

    def status(self, update_id: str | None = None) -> dict:
        """Read an update record and at most 64 KiB of its log."""
        if update_id is None:
            path = max(self.directory.glob("*/record.json"), key=lambda item: item.stat().st_mtime_ns, default=None)
            if path is None:
                return {"record": None, "log": ""}
        else:
            if len(update_id) != 32 or any(char not in "0123456789abcdef" for char in update_id):
                raise ValueError("Invalid update_id")
            path = self.directory / update_id / "record.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        log_path = path.with_name("update.log")
        log = ""
        if log_path.exists():
            with log_path.open("rb") as stream:
                stream.seek(max(0, os.fstat(stream.fileno()).st_size - 65536))
                log = stream.read(65536).decode("utf-8", errors="replace")
        return {"record": record, "log": log}
