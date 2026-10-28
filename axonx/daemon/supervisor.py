"""Standalone supervisor. This file must import only the Python standard library."""

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

# Support both package imports and the copied script launched with python -S.
if __package__:
    from .update import save, signal_group
else:
    from update import save, signal_group

PREFIX = "AXONX_DAEMON_"
SHUTDOWN_TIMEOUT = 5


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

    @staticmethod
    def _spawn(command, cwd, environment, log_file: Path) -> subprocess.Popen:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("ab") as output:
            return subprocess.Popen(  # pylint: disable=consider-using-with
                command,
                cwd=cwd,
                env=environment,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=output,
            )

    def _start(self):
        self.token = uuid4().hex
        environment = {
            **self.plan["environment"],
            "PYTHONUNBUFFERED": "1",
            PREFIX + "DIRECTORY": str(self.directory),
            PREFIX + "SOCKET": self.plan["socket"],
            PREFIX + "TOKEN": self.token,
        }
        try:
            self.service = self._spawn(
                self.plan["command"], self.plan["cwd"], environment, self.directory / "service.log"
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

    @contextmanager
    def _console_output(self):
        """Follow new service output without blocking supervision on a slow terminal."""
        finished = threading.Event()
        log = (self.directory / "service.log").open("a+b")
        log.seek(0, os.SEEK_END)
        console = sys.stdout.fileno()

        def forward():
            with log:
                try:
                    while True:
                        stopping = finished.is_set()
                        data = log.read(65536)
                        if data:
                            while data:
                                data = data[os.write(console, data) :]
                        elif stopping:
                            return
                        else:
                            finished.wait(0.05)
                except OSError:
                    # A closed console must not interrupt the service or its file log.
                    return

        thread = threading.Thread(target=forward, name="service-console", daemon=True)
        thread.start()
        try:
            yield
        finally:
            finished.set()
            thread.join(timeout=1)

    def _stop(self):
        self.token = None
        self.ready = False
        if self.service is not None:
            signal_group(self.service.pid, signal.SIGTERM)
            self.deadline = time.monotonic() + self.stop_timeout

    def force_exit(self):
        """Enforce the daemon's total shutdown limit without waiting on cleanup or logs."""
        try:
            for child in (self.service, self.update):
                if child is not None:
                    signal_group(child.pid)
        finally:
            os._exit(130)

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
        shutil.copyfile(message["worker"], folder / "update.py")
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
        environment = {key: value for key, value in environment.items() if not key.startswith(PREFIX)}
        child = self._spawn(command, cwd, environment, Path(log_file))
        self.tasks[child.pid] = child
        self._state()
        return {"pid": child.pid}

    def handle(self, message):
        if not isinstance(message, dict):
            raise ValueError("Invalid daemon message")
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

    def _poll_service(self, now):
        if self.service is not None:
            child = self.service
            if child.poll() is None:
                if now > self.deadline:
                    signal_group(child.pid)
            else:
                signal_group(child.pid)
                self.service = None
                self.token = None
                self.ready = False
                self.deadline = float("inf")
                self.failures += 1
                self.retry = now + min(30, 2 ** min(self.failures, 5))
                if self.pending is not None and self.phase in {"starting", "running"}:
                    self._settle(f"Service exited before startup completed (exit {child.returncode}); see service.log")
                self._state()

    def _poll_update(self):
        """Replace the stopped service after an update, or a plain restart."""
        if self.pending is None:
            return
        if self.phase == "restarting" and self.service is None:
            record = json.loads(self.pending.read_text(encoding="utf-8"))
            self.phase = "starting"
            if record["mode"] == "restart":
                record["phase"] = "starting"
                save(self.pending, record)
            else:
                try:
                    self.update = self._spawn(
                        [self.plan["python"], str(self.pending.with_name("update.py")), str(self.pending)],
                        self.plan["cwd"],
                        self.plan["environment"],
                        self.pending.with_name("update.log"),
                    )
                    self.phase = "updating"
                except OSError as exc:
                    record.update(phase="failed", error=f"Cannot start updater: {exc}")
                    save(self.pending, record)
            self._state()
        if self.update is not None and self.update.poll() is not None:
            if self.update.returncode:
                record = json.loads(self.pending.read_text(encoding="utf-8"))
                if record["phase"] != "failed":
                    record.update(
                        phase="failed", error=f"Updater exited with code {self.update.returncode}; see update.log"
                    )
                    save(self.pending, record)
            self.update = None
            self.phase = "starting"

    def _poll(self):
        now = time.monotonic()
        if self.pending is not None and self.phase == "running" and now > self.commit_deadline:
            self._settle("Update response did not commit within 60 seconds")
            self._stop()
        self._poll_service(now)
        for pid, child in list(self.tasks.items()):
            if child.poll() is not None:
                print(f"Task process exited pid={pid} exit_code={child.returncode}", flush=True)
                self.tasks.pop(pid)
                self._state()
        if self.stopping:
            return
        self._poll_update()
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
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server, self._console_output():
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
    watchdog = threading.Timer(SHUTDOWN_TIMEOUT, supervisor.force_exit)
    watchdog.daemon = True
    interrupted = False

    def stop(_signum, _frame):
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            watchdog.start()
        supervisor.stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        supervisor.run()
    finally:
        watchdog.cancel()


if __name__ == "__main__":
    main()
