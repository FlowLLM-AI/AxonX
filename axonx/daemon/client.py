"""Small local client and launcher for the standalone daemon."""

import fcntl
import hashlib
import json
import os
import shutil
import socket
import tempfile
from pathlib import Path

DIRECTORY = "AXONX_DAEMON_DIRECTORY"
SOCKET = "AXONX_DAEMON_SOCKET"
TOKEN = "AXONX_DAEMON_TOKEN"
ROLE = "AXONX_DAEMON_ROLE"


def runtime_directory(workspace: str, host: str, port: int, cwd: Path) -> Path:
    identity = f"{socket.gethostname()}:{host}:{port}:{cwd}"
    key = hashlib.sha256(identity.encode()).hexdigest()[:16]
    return Path(workspace).expanduser().resolve() / "daemon" / key


def request(action: str, **values):
    """Use one bounded JSON exchange; failed requests are never retried."""
    if not os.environ.get(SOCKET) or not os.environ.get(TOKEN):
        raise RuntimeError("This operation requires a daemon started with axonx start")
    message = {"action": action, "token": os.environ[TOKEN], **values}
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


def launch(plan: dict, directory: Path) -> None:
    """Replace the launcher with a private, standard-library-only snapshot."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "daemon.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"AxonX is already running: {directory}") from exc
        digest = hashlib.sha256(str(directory).encode()).hexdigest()[:16]
        plan.update(
            directory=str(directory), socket=str(Path(tempfile.gettempdir()) / f"axonx-{os.getuid()}-{digest}.sock")
        )
        path = directory / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        worker = directory / "daemon.py"
        shutil.copyfile(Path(__file__).with_name("worker.py"), worker)
        os.set_inheritable(lock.fileno(), True)
        os.execve(
            plan["python"], [plan["python"], "-S", str(worker), str(path), str(lock.fileno())], plan["environment"]
        )
