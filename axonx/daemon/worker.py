"""Standalone supervisor. This file must import only the Python standard library."""

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

PREFIX = "AXONX_DAEMON_"


def save(path: Path, value: dict) -> None:
    value["updated_at"] = datetime.now(UTC).isoformat()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


class Supervisor:
    """Restart one service and reap one-shot commands without interpreting Tasks."""

    def __init__(self, plan: dict):
        self.plan = plan
        self.directory = Path(plan["directory"])
        self.service: subprocess.Popen | None = None
        self.token: str | None = None
        self.ready = False
        self.deadline = float("inf")
        self.retry = 0.0
        self.failures = 0
        self.tasks: dict[int, subprocess.Popen] = {}
        self.pending: Path | None = None
        self.commit_deadline = 0.0
        self.phase = "running"
        self.update: subprocess.Popen | None = None
        self.stopping = False
        self.stop_timeout = plan["stop_timeout"]

    def _state(self):
        save(
            self.directory / "processes.json",
            {
                "pid": os.getpid(),
                "phase": self.phase,
                "service": self.service.pid if self.service else None,
                "ready": self.ready,
                "tasks": list(self.tasks),
            },
        )

    def _start(self):
        self.token = uuid4().hex
        environment = {
            **self.plan["environment"],
            PREFIX + "DIRECTORY": str(self.directory),
            PREFIX + "SOCKET": self.plan["socket"],
            PREFIX + "TOKEN": self.token,
        }
        try:
            with (self.directory / "service.log").open("ab") as output:
                self.service = subprocess.Popen(  # pylint: disable=consider-using-with
                    self.plan["command"],
                    cwd=self.plan["cwd"],
                    env=environment,
                    start_new_session=True,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=output,
                )
        except OSError as exc:
            self.token = None
            self.retry = time.monotonic() + 5
            print(f"Cannot start service: {exc}", file=sys.stderr, flush=True)
            if self.pending is not None:
                self._settle(f"Cannot start service: {exc}")
            return
        self.deadline = time.monotonic() + 120
        self._state()

    def _stop(self):
        self.token = None
        self.ready = False
        if self.service is not None:
            try:
                os.killpg(self.service.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            self.deadline = time.monotonic() + self.stop_timeout

    def _settle(self, error=None):
        if self.pending is not None:
            record = json.loads(self.pending.read_text(encoding="utf-8"))
            if error:
                record.update(phase="failed", error=error)
            elif record["phase"] != "failed":
                record.update(phase="succeeded", error=None)
            save(self.pending, record)
        self.pending = None
        self.phase = "running"
        self._state()

    def _prepare(self, message):
        if self.pending is not None:
            raise RuntimeError("An update is already pending")
        mode = message["mode"]
        if mode not in {"git", "pip", "restart"}:
            raise ValueError("Unknown update mode")
        folder = self.directory / "updates" / uuid4().hex
        folder.mkdir(parents=True, mode=0o700)
        shutil.copyfile(message["worker"], folder / "worker.py")
        save(folder / "plan.json", message["plan"])
        record = {
            "update_id": folder.name,
            "mode": mode,
            "phase": "accepted",
            "error": None,
            "created_at": datetime.now(UTC).isoformat(),
            "before": message["versions"],
            "after": None,
            "commit": None,
        }
        path = folder / "record.json"
        save(path, record)
        self.pending = path
        self.commit_deadline = time.monotonic() + 60
        return record

    def _exec(self, message):
        if self.pending is not None or not self.ready:
            raise RuntimeError("Scheduled launches are paused")
        command = message["command"]
        cwd, environment, log_file = message["cwd"], message["environment"], message["log_file"]
        if not isinstance(command, list) or not command or not all(isinstance(arg, str) for arg in command):
            raise ValueError("Invalid exec command")
        if (
            not isinstance(environment, dict)
            or not all(isinstance(key, str) and isinstance(value, str) for key, value in environment.items())
            or not all(isinstance(value, str) for value in (cwd, log_file))
        ):
            raise ValueError("Invalid exec environment")
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        environment = {key: value for key, value in environment.items() if not key.startswith(PREFIX)}
        with path.open("ab") as output:
            child = subprocess.Popen(  # pylint: disable=consider-using-with
                command,
                cwd=cwd,
                env=environment,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=output,
            )
        self.tasks[child.pid] = child
        self._state()
        return {"pid": child.pid}

    def handle(self, message):
        if self.token is None or self.token != message.get("token"):
            raise ValueError("Expired or invalid service token")
        action = message["action"]
        if action == "ready":
            self.stop_timeout = message["stop_timeout"]
            if self.pending is not None:
                record = json.loads(self.pending.read_text(encoding="utf-8"))
                record["after"] = message["versions"]
                save(self.pending, record)
            self.ready = True
            self.failures = 0
            self.deadline = float("inf")
            self._state()
            return None
        if action == "exec":
            return self._exec(message)
        if action == "prepare_update":
            return self._prepare(message)
        if action == "commit_update":
            if self.pending is None or self.pending.parent.name != message["update_id"] or self.phase != "running":
                raise ValueError("Update is not awaiting commit")
            self.phase = "restarting"
            self._stop()
            self._state()
            return None
        raise ValueError(f"Unsupported daemon action: {action}")

    def _poll(self):
        now = time.monotonic()
        if self.pending is not None and self.phase == "running" and now > self.commit_deadline:
            self._settle("Update response did not commit within 60 seconds")
            self._stop()
        if self.service is not None:
            child = self.service
            if child.poll() is None:
                if now > self.deadline:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            else:
                self.service = None
                self.token = None
                self.ready = False
                self.deadline = float("inf")
                self.failures += 1
                self.retry = now + min(30, 2 ** min(self.failures, 5))
                if self.pending is not None and self.phase in {"starting", "running"}:
                    self._settle(f"Service exited before startup completed (exit {child.returncode}); see service.log")
                self._state()
        for pid, child in list(self.tasks.items()):
            if child.poll() is not None:
                print(f"Task process exited pid={pid} exit_code={child.returncode}", flush=True)
                self.tasks.pop(pid)
                self._state()
        if self.stopping:
            return
        if self.phase == "restarting" and self.service is None:
            record = json.loads(self.pending.read_text(encoding="utf-8"))
            if record["mode"] == "restart":
                record["phase"] = "starting"
                save(self.pending, record)
                self.phase = "starting"
            else:
                try:
                    self.update = subprocess.Popen(  # pylint: disable=consider-using-with
                        [self.plan["python"], str(self.pending.with_name("worker.py")), str(self.pending)],
                        cwd=self.plan["cwd"],
                        env=self.plan["environment"],
                        start_new_session=True,
                        stdin=subprocess.DEVNULL,
                    )
                    self.phase = "updating"
                except OSError as exc:
                    record.update(phase="failed", error=f"Cannot start updater: {exc}")
                    save(self.pending, record)
                    self.phase = "starting"
            self._state()
        if self.phase == "updating" and self.update.poll() is not None:
            if self.update.returncode:
                record = json.loads(self.pending.read_text(encoding="utf-8"))
                if record["phase"] != "failed":
                    record.update(
                        phase="failed", error=f"Updater exited with code {self.update.returncode}; see update.log"
                    )
                    save(self.pending, record)
            self.update = None
            self.phase = "starting"
        if self.phase in {"running", "starting"}:
            if self.service is None and (self.phase == "starting" or now >= self.retry):
                self._start()
            if self.phase == "starting" and self.ready:
                self._settle()

    def run(self):
        """Serve local control requests and reap children until explicitly stopped."""
        path = Path(self.plan["socket"])
        path.unlink(missing_ok=True)
        # Incomplete operations belong to an earlier daemon; never resume them implicitly.
        for record_path in (self.directory / "updates").glob("*/record.json"):
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if record["phase"] not in {"succeeded", "failed"}:
                record.update(phase="failed", error="Daemon stopped before update completed")
                save(record_path, record)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            mask = os.umask(0o077)
            try:
                server.bind(str(path))
            finally:
                os.umask(mask)
            server.listen()
            server.settimeout(0.2)
            try:
                while not self.stopping:
                    self._poll()
                    try:
                        connection, _address = server.accept()
                    except socket.timeout:
                        continue
                    with connection:
                        connection.settimeout(2)
                        with connection.makefile("rwb") as stream:
                            try:
                                message = json.loads(stream.readline(1024 * 1024))
                                result = {"answer": self.handle(message)}
                            except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
                                result = {"error": str(exc)}
                            try:
                                stream.write(json.dumps(result).encode() + b"\n")
                                stream.flush()
                            except OSError:
                                pass
            finally:
                self.stopping = True
                self._stop()
                if self.update is not None:
                    self.update.terminate()
                while self.service is not None:
                    self._poll()
                    time.sleep(0.05)
                if self.update is not None:
                    try:
                        self.update.wait(timeout=self.stop_timeout)
                    except subprocess.TimeoutExpired:
                        self.update.kill()
                        self.update.wait()
                self._settle("Daemon stopped before update completed")
                path.unlink(missing_ok=True)


def main():
    os.set_inheritable(int(sys.argv[2]), False)
    supervisor = Supervisor(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))

    def stop(_signum, _frame):
        supervisor.stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    supervisor.run()


if __name__ == "__main__":
    main()
