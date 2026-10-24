"""Real daemon ownership, worker replacement and uninterrupted Task execution."""

import ast
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from zipfile import ZipFile

import psutil
import pytest
from test_plugin_hot_update import wheel

from axonx.daemon import client
from axonx.daemon.worker import Supervisor
from axonx.task.storage.workspace import read_entry


def plan(tmp_path):
    return {
        "directory": str(tmp_path),
        "socket": str(tmp_path / "daemon.sock"),
        "cwd": str(tmp_path),
        "python": sys.executable,
        "command": [sys.executable, "-c", "pass"],
        "environment": dict(os.environ),
        "stop_timeout": 1,
    }


def test_daemon_snapshot_imports_only_standard_library():
    path = Path(__file__).parents[2] / "axonx" / "daemon" / "worker.py"
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in sys.stdlib_module_names for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module.split(".")[0] in sys.stdlib_module_names


def test_stale_workers_cannot_start_tasks_or_commit_updates(tmp_path):
    supervisor = Supervisor(plan(tmp_path))
    supervisor.tokens["cron"] = "current"
    with pytest.raises(ValueError, match="Expired"):
        supervisor.handle({"action": "exec", "token": "old", "arguments": ["--task", "demo"], "line": 1})
    with pytest.raises(RuntimeError, match="paused"):
        supervisor.handle({"action": "exec", "token": "current", "arguments": ["--task", "demo"], "line": 1})
    assert not supervisor.tasks
    with pytest.raises(ValueError, match="Unsupported"):
        supervisor.handle({"action": "prepare_update", "token": "current"})


def test_update_reservation_is_serial_and_requires_response_commit(tmp_path):
    supervisor = Supervisor(plan(tmp_path))
    supervisor.tokens["service"] = "current"
    worker = tmp_path / "updater.py"
    worker.write_text("raise SystemExit(0)")
    message = {
        "action": "prepare_update",
        "token": "current",
        "mode": "restart",
        "plan": {},
        "worker": str(worker),
        "versions": {},
    }
    record = supervisor.handle(message)
    assert supervisor.phase == "running"
    assert supervisor.update is None
    assert record["phase"] == "accepted"
    with pytest.raises(RuntimeError, match="already pending"):
        supervisor.handle(message)
    with pytest.raises(ValueError, match="awaiting commit"):
        supervisor.handle({"action": "commit_update", "token": "current", "update_id": "wrong"})
    supervisor.handle({"action": "commit_update", "token": "current", "update_id": record["update_id"]})
    assert supervisor.phase == "quiescing"


def wait_for(predicate, output, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = predicate()
            if result:
                return result
        except (FileNotFoundError, json.JSONDecodeError, urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.05)
    return pytest.fail(output())


def test_real_daemon_restarts_workers_without_interrupting_cron_task(tmp_path):
    source = Path(__file__).parents[2]
    site = tmp_path / "site"
    site.mkdir()
    release = tmp_path / "finish-task"
    artifact = wheel(
        tmp_path,
        "daemon_slow",
        {"task.py": """import os,time
from pathlib import Path
from axonx.task.builtins.demo import DemoTask
class Slow(DemoTask):
    def initialize(self):
        assert not any(name.startswith("AXONX_DAEMON_") for name in os.environ)
        while not Path(os.environ["TEST_FINISH_TASK"]).exists():
            time.sleep(0.05)
        super().initialize()
"""},
        {"daemon_slow": "daemon_slow.task:Slow"},
    )
    with ZipFile(artifact) as archive:
        archive.extractall(site)
    # Exercise real cron -> IPC -> daemon Popen without waiting for a wall-clock minute.
    (site / "sitecustomize.py").write_text("""import os
if os.environ.get("AXONX_DAEMON_ROLE") == "service":
    from axonx.components.updater import manager
    manager.UpdateManager._plan = lambda self, mode, service: {"cwd": str(service.startup_directory)}
    manager.__file__ = os.environ["TEST_UPDATE_SOURCE"]
if os.environ.get("AXONX_DAEMON_ROLE") == "cron":
    import asyncio
    from pathlib import Path
    from datetime import datetime
    from axonx.cron.scheduler import CronScheduler
    async def run(self):
        await asyncio.sleep(0.2)
        marker = Path(os.environ["TEST_CRON_TRIGGERED"])
        if not marker.exists():
            marker.touch()
            now = datetime.now(self.timezone)
            self._next = {entry.line: now for entry in self.entries}
            self._tick(now)
        await asyncio.Event().wait()
    CronScheduler._run = run
""")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    config = tmp_path / "app.yaml"
    config.write_text(f"""extends: default
workspace_dir: {tmp_path / "workspace"}
log_dir: {tmp_path / "logs"}
log_to_console: false
log_to_file: false
enable_logo: false
components:
  agent: {{}}
service:
  host: 127.0.0.1
  port: {port}
  token: test-secret
  web_enabled: false
""")
    cron = tmp_path / "tasks.cron"
    cron.write_text("* * * * * axonx exec --task daemon_slow --task-name survives --x 2 --y 3\n")
    updater_source = tmp_path / "updater"
    updater_source.mkdir()
    (updater_source / "worker.py").write_text("""import json,os,sys,time
from pathlib import Path
path = Path(sys.argv[1])
record = json.loads(path.read_text())
record["phase"] = "installing"
path.write_text(json.dumps(record))
Path(os.environ["TEST_UPDATE_RAN"]).touch()
time.sleep(0.3)
record["phase"] = "starting"
path.write_text(json.dumps(record))
""")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("AXONX_DAEMON_")}
    environment.update(
        PYTHONPATH=os.pathsep.join([str(site), str(source)]),
        TEST_FINISH_TASK=str(release),
        TEST_UPDATE_SOURCE=str(updater_source / "manager.py"),
        TEST_UPDATE_RAN=str(tmp_path / "updated"),
        TEST_CRON_TRIGGERED=str(tmp_path / "triggered"),
    )
    directory = client.runtime_directory(str(tmp_path / "workspace"), "127.0.0.1", port, tmp_path)
    output = tmp_path / "launcher.log"

    def logs():
        return "\n".join(path.read_text(errors="replace") for path in [output, *directory.glob("*.log")])

    def state():
        return json.loads((directory / "processes.json").read_text())

    def invoke(job):
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/jobs/{job}",
            data=b'{"arguments":{}}',
            headers={"Authorization": "Bearer test-secret", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            return json.load(response)

    task_id = "base#daemon_slow#survives"
    with output.open("w") as stream:
        process = subprocess.Popen(  # pylint: disable=consider-using-with
            [sys.executable, "-m", "axonx.cli", "start", "--config", str(config), "--cron", str(cron)],
            cwd=tmp_path,
            env=environment,
            stdout=stream,
            stderr=stream,
        )
        task_pid = None
        try:
            initial = wait_for(lambda: (value if value.get("cron") else None) if (value := state()) else None, logs)
            assert initial["pid"] == process.pid
            running = wait_for(
                lambda: (
                    value
                    if (value := read_entry(tmp_path / "workspace", task_id)) and value.state == "running"
                    else None
                ),
                logs,
            )
            task_pid, run_id = running.pid, running.run_id
            assert psutil.Process(task_pid).ppid() == process.pid
            assert invoke("version")["success"]
            accepted = invoke("restart_service")
            assert accepted["success"] and accepted["answer"]["phase"] == "accepted"

            def restarted():
                value = state()
                record = invoke("get_update_status")["answer"]["record"]
                return (
                    value
                    if (
                        value.get("service") != initial["service"]
                        and value.get("cron")
                        and value.get("cron") != initial["cron"]
                        and record["phase"] == "succeeded"
                    )
                    else None
                )

            updated = wait_for(restarted, logs)
            assert process.poll() is None
            assert psutil.Process(task_pid).ppid() == process.pid
            assert read_entry(tmp_path / "workspace", task_id).run_id == run_id
            previous = updated
            accepted_update = invoke("update_from_pip")
            assert accepted_update["success"]

            def installed():
                value = state()
                record = invoke("get_update_status")["answer"]["record"]
                return (
                    value
                    if (
                        record["update_id"] == accepted_update["answer"]["update_id"]
                        and record["phase"] == "succeeded"
                        and value.get("service") != previous["service"]
                        and value.get("cron") not in (None, previous["cron"])
                    )
                    else None
                )

            updated = wait_for(installed, logs)
            assert (tmp_path / "updated").exists()
            assert psutil.Process(task_pid).is_running()
            # A service crash and a cron crash also leave the same Task running.
            os.kill(updated["service"], signal.SIGKILL)
            wait_for(
                lambda: state().get("service") not in (None, updated["service"]) and invoke("version")["success"], logs
            )
            os.kill(updated["cron"], signal.SIGKILL)
            wait_for(lambda: state().get("cron") not in (None, updated["cron"]), logs)
            assert psutil.Process(task_pid).is_running()
            release.touch()
            finished = wait_for(
                lambda: (
                    value
                    if (value := read_entry(tmp_path / "workspace", task_id)) and value.state.is_terminal
                    else None
                ),
                logs,
            )
            assert finished.state == "succeeded"
            assert finished.run_id == run_id
            assert finished.output_params["result"] == 5
            wait_for(lambda: not state()["tasks"], logs)
        finally:
            release.touch()
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            if task_pid is not None:
                wait_for(
                    lambda: not psutil.pid_exists(task_pid)
                    or psutil.Process(task_pid).status() == psutil.STATUS_ZOMBIE,
                    logs,
                    timeout=10,
                )


def test_abandoned_update_reservation_expires_without_starting_update(tmp_path, monkeypatch):
    supervisor = Supervisor(plan(tmp_path))
    worker = tmp_path / "updater.py"
    worker.write_text("raise SystemExit(0)")
    record = supervisor._prepare({"mode": "restart", "worker": str(worker), "plan": {}, "versions": {}})
    supervisor.commit_deadline = 0
    monkeypatch.setattr(supervisor, "_start", lambda *_: None)
    supervisor._poll()
    path = tmp_path / "updates" / record["update_id"] / "record.json"
    assert json.loads(path.read_text())["phase"] == "failed"
    assert supervisor.pending is None
    assert supervisor.update is None


def test_unexpected_updater_exit_cannot_be_reported_as_success(tmp_path, monkeypatch):
    from types import SimpleNamespace

    supervisor = Supervisor(plan(tmp_path))
    worker = tmp_path / "updater.py"
    worker.write_text("raise SystemExit(7)")
    record = supervisor._prepare({"mode": "pip", "worker": str(worker), "plan": {}, "versions": {}})
    supervisor.phase = "updating"
    supervisor.update = SimpleNamespace(poll=lambda: 7, returncode=7)
    monkeypatch.setattr(supervisor, "_start", lambda *_: None)
    supervisor._poll()
    supervisor._settle()
    path = tmp_path / "updates" / record["update_id"] / "record.json"
    saved = json.loads(path.read_text())
    assert saved["phase"] == "failed"
    assert "7" in saved["error"]
