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
    """Own worker processes and exec children, without interpreting Task metadata."""

    def __init__(self, plan: dict):
        self.plan = plan
        self.directory = Path(plan["directory"])
        self.children: dict[str, subprocess.Popen] = {}
        self.tokens: dict[str, str] = {}
        self.ready: set[str] = set()
        self.deadlines: dict[str, float] = {}
        self.retry: dict[str, float] = {}
        self.failures: dict[str, int] = {}
        self.tasks: dict[int, subprocess.Popen] = {}
        self.execution: dict = {}
        self.has_cron = False
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
                **{role: child.pid for role, child in self.children.items()},
                "tasks": list(self.tasks),
            },
        )

    def _start(self, role):
        token = uuid4().hex
        environment = {
            **self.plan["environment"],
            PREFIX + "DIRECTORY": str(self.directory),
            PREFIX + "SOCKET": self.plan["socket"],
            PREFIX + "TOKEN": token,
            PREFIX + "ROLE": role,
        }
        try:
            with (self.directory / f"{role}.log").open("ab") as output:
                child = subprocess.Popen(  # pylint: disable=consider-using-with
                    self.plan["command"],
                    cwd=self.plan["cwd"],
                    env=environment,
                    start_new_session=True,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=output,
                )
        except OSError as exc:
            self.retry[role] = time.monotonic() + 5
            print(f"Cannot start {role}: {exc}", file=sys.stderr, flush=True)
            if self.pending is not None:
                self._settle(f"Cannot start {role}: {exc}")
            return
        self.children[role] = child
        self.tokens[role] = token
        self.deadlines[role] = time.monotonic() + 120
        self._state()

    def _stop(self, role):
        child = self.children.get(role)
        self.tokens.pop(role, None)
        self.ready.discard(role)
        if child is not None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            self.deadlines[role] = time.monotonic() + self.stop_timeout

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
        if self.pending is not None or "cron" not in self.ready:
            raise RuntimeError("Cron is paused")
        command, line = message["command"], message["line"]
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(arg, str) for arg in command)
            or not isinstance(line, int)
            or line < 1
        ):
            raise ValueError("Invalid cron exec request")
        directory = Path(self.execution["log_dir"]) / "cron"
        directory.mkdir(parents=True, exist_ok=True)
        environment = {key: value for key, value in self.execution["environment"].items() if not key.startswith(PREFIX)}
        with (directory / f"line-{line}.log").open("ab") as output:
            child = subprocess.Popen(  # pylint: disable=consider-using-with
                command,
                cwd=self.execution["cwd"],
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
        role = next((name for name, token in self.tokens.items() if token == message.get("token")), None)
        if role is None:
            raise ValueError("Expired or invalid worker token")
        action = message["action"]
        if action == "ready":
            if role == "service":
                self.has_cron = message["cron"]
                if not self.has_cron:
                    self._stop("cron")
                self.stop_timeout = message["stop_timeout"]
                if self.pending is not None:
                    record = json.loads(self.pending.read_text(encoding="utf-8"))
                    record["after"] = message["versions"]
                    save(self.pending, record)
            else:
                self.execution = message["execution"]
            self.ready.add(role)
            self.failures[role] = 0
            self.deadlines.pop(role, None)
            self._state()
            return None
        if action == "exec" and role == "cron":
            return self._exec(message)
        if action == "prepare_update" and role == "service":
            return self._prepare(message)
        if action == "commit_update" and role == "service":
            if self.pending is None or self.pending.parent.name != message["update_id"] or self.phase != "running":
                raise ValueError("Update is not awaiting commit")
            self.phase = "quiescing"
            self._stop("cron")
            self._state()
            return None
        raise ValueError(f"Unsupported daemon action: {action}")

    def _poll(self):
        now = time.monotonic()
        if self.pending is not None and self.phase == "running" and now > self.commit_deadline:
            self._settle("Update response did not commit within 60 seconds")
            self._stop("service")
        for role, child in list(self.children.items()):
            if child.poll() is None:
                if now > self.deadlines.get(role, float("inf")):
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                continue
            self.children.pop(role)
            self.tokens.pop(role, None)
            self.ready.discard(role)
            self.deadlines.pop(role, None)
            self.failures[role] = self.failures.get(role, 0) + 1
            self.retry[role] = now + min(30, 2 ** min(self.failures[role], 5))
            if self.pending is not None and (
                self.phase == "starting" or (role == "service" and self.phase == "running")
            ):
                self._settle(f"{role} exited before startup completed (exit {child.returncode}); see {role}.log")
            self._state()
        for pid, child in list(self.tasks.items()):
            if child.poll() is not None:
                print(f"Task process exited pid={pid} exit_code={child.returncode}", flush=True)
                self.tasks.pop(pid)
                self._state()
        if self.stopping:
            return
        if self.phase == "quiescing" and "cron" not in self.children:
            record = json.loads(self.pending.read_text(encoding="utf-8"))
            if record["mode"] == "restart":
                record["phase"] = "starting"
                save(self.pending, record)
                self.phase = "restarting"
                self._stop("service")
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
                    self.phase = "restarting"
                    self._stop("service")
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
            self.phase = "restarting"
            self._stop("service")
        if self.phase == "restarting" and "service" not in self.children:
            self.phase = "starting"
            self._start("service")
        if self.phase in {"running", "starting"}:
            if "service" not in self.children and now >= self.retry.get("service", 0):
                self._start("service")
            if "service" in self.ready:
                if self.has_cron and "cron" not in self.children and now >= self.retry.get("cron", 0):
                    self._start("cron")
                if self.phase == "starting" and (not self.has_cron or "cron" in self.ready):
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
                for role in list(self.children):
                    self._stop(role)
                if self.update is not None:
                    self.update.terminate()
                while self.children:
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
