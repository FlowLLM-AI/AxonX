"""Validate the thin CLI through a real daemon-supervised application."""

import json
import os
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from textwrap import dedent
from time import monotonic, sleep

import httpx
import psutil
import pytest
import yaml

from axonx.app.config.resolver import resolve_app_config
from axonx.daemon import client as daemon
from axonx.daemon.client import runtime_directory
from axonx.daemon.update import UpdateClient
from axonx.task.storage.workspace import task_path


def test_cli_validates_the_complete_crontab_before_launching_workers(tmp_path, monkeypatch, capsys):
    from axonx.cli.main import main
    from axonx.daemon import launcher

    monkeypatch.delenv(daemon.SOCKET, raising=False)
    monkeypatch.delenv("AXONX_CLI_REQUEST_ID", raising=False)
    monkeypatch.setattr(launcher, "load_env", lambda: {})
    launches = []
    monkeypatch.setattr(daemon, "launch", lambda *args: launches.append(args))
    config, crontab = tmp_path / "app.yaml", tmp_path / "commands.cron"
    config.write_text(yaml.safe_dump({"workspace_dir": str(tmp_path), "service": {"backend": "http"}}))
    crontab.write_text(
        "\n".join(
            (
                "* * * * * axonx exec --task demo --x 1",
                "* * * * * axonx exec --task demo --target remote:1024",
            )
        )
    )
    argv = ["start", "--config", str(config), "--cron", str(crontab)]
    assert main(argv) == 2
    assert not launches
    assert f"{crontab}:2:" in capsys.readouterr().err
    crontab.write_text("* * * * * axonx exec --task demo --x 1\n")
    assert main(argv) == 0
    assert len(launches) == 1


def test_update_client_prepares_and_commits_without_application_objects(tmp_path, monkeypatch):
    calls = []

    def request(action, **values):
        calls.append((action, values))
        return {"update_id": "a" * 32}

    monkeypatch.setenv(daemon.SOCKET, "test-socket")
    monkeypatch.setattr(daemon, "request", request)
    updates = UpdateClient(tmp_path, tmp_path, "assert True")
    record = updates.prepare("restart")
    updates.commit(record["update_id"])
    assert [action for action, _ in calls] == ["prepare_update", "commit_update"]
    assert calls[0][1]["plan"] == {"cwd": str(tmp_path), "verification": "assert True"}
    assert updates.status() == {"record": None, "log": ""}


def test_cli_start_supervises_one_app_and_injects_the_command_driver(tmp_path):
    root = Path(__file__).resolve().parents[2]
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    workspace = tmp_path / "workspace"
    defaults = resolve_app_config(log_config=False)
    config = {
        "workspace_dir": str(workspace),
        "log_dir": str(tmp_path / "logs"),
        "log_to_console": False,
        "log_to_file": False,
        "enable_logo": False,
        "components": {name: defaults["components"][name] for name in ("task_index", "updater")},
        "jobs": {name: defaults["jobs"][name] for name in ("cli", "status", "get_update_status")},
        "service": {
            "backend": "http",
            "host": "127.0.0.1",
            "port": port,
            "token": "test-token",
            "web_enabled": False,
            "cleanup_timeout": 2,
        },
    }
    configuration, crontab = tmp_path / "app.yaml", tmp_path / "empty.cron"
    configuration.write_text(yaml.safe_dump(config))
    crontab.write_text("# Start the in-process Cron component without firing tasks.\n")
    directory = runtime_directory(str(workspace), "127.0.0.1", port, tmp_path)
    environment = {key: value for key, value in os.environ.items() if not key.startswith("AXONX_DAEMON_")}
    environment["PYTHONPATH"] = str(root)
    children = []
    with (tmp_path / "daemon.log").open("w+") as output:
        with subprocess.Popen(
            [sys.executable, "-m", "axonx.cli", "start", "--config", str(configuration), "--cron", str(crontab)],
            cwd=tmp_path,
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
        ) as process:
            try:
                with httpx.Client(
                    base_url=f"http://127.0.0.1:{port}",
                    headers={"Authorization": "Bearer test-token"},
                    timeout=1,
                    trust_env=False,
                ) as client:
                    deadline = monotonic() + 20
                    ready = False
                    while monotonic() < deadline and process.poll() is None:
                        try:
                            state = json.loads((directory / "processes.json").read_text())
                            health = client.get("/health").json()
                            if state["ready"] and health["answer"]["running"]:
                                assert "cron" not in state
                                children = [psutil.Process(state["service"])]
                                ready = True
                                break
                        except (OSError, ValueError, KeyError, httpx.HTTPError):
                            pass
                        sleep(0.05)
                    if not ready:
                        logs = [path.read_text() for path in directory.glob("*.log")]
                        output.seek(0)
                        raise AssertionError("Workers did not start:\n" + output.read() + "\n".join(logs))
                    response = client.post(
                        "/jobs/cli",
                        timeout=10,
                        json={
                            "arguments": {
                                "argv": [
                                    "exec",
                                    "--task",
                                    "demo",
                                    "--task-name",
                                    "daemon",
                                    "--x",
                                    "3",
                                    "--y",
                                    "4",
                                ]
                            }
                        },
                    ).json()
                    assert response["success"], response
                    assert json.loads(response["answer"]["stdout"])["result"] == 7
                    status = client.post("/jobs/status", json={"arguments": {"task_id": "base#demo#daemon"}}).json()
                    assert status["answer"]["output_params"]["result"] == 7
                    update = client.post("/jobs/get_update_status", json={"arguments": {}}).json()
                    assert update["success"]
                    assert update["answer"]["record"] is None
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
                    for child in children:
                        if child.is_running() and child.status() != psutil.STATUS_ZOMBIE:
                            child.terminate()
                    _, alive = psutil.wait_procs(children, timeout=5)
                    for child in alive:
                        child.kill()
                    psutil.wait_procs(alive, timeout=5)


def test_invalid_advertised_target_is_rejected_before_launching_workers(tmp_path, monkeypatch, capsys):
    from axonx.cli.main import main
    from axonx.daemon import launcher

    monkeypatch.delenv(daemon.SOCKET, raising=False)
    monkeypatch.delenv("AXONX_CLI_REQUEST_ID", raising=False)
    monkeypatch.setattr(launcher, "load_env", lambda: {})
    launches = []
    monkeypatch.setattr(daemon, "launch", lambda *args: launches.append(args))
    config = tmp_path / "app.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "workspace_dir": str(tmp_path),
                "service": {"backend": "http"},
                "environment": {"AXONX_TASK_EXECUTION_TARGET": "127.0.0.1:1024"},
            }
        )
    )
    assert main(["start", "--config", str(config)]) == 2
    assert not launches
    assert "execution_target" in capsys.readouterr().err


def eventually(read, timeout=20):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        try:
            if value := read():
                return value
        except (OSError, ValueError, KeyError, httpx.HTTPError):
            pass
        sleep(0.05)
    raise AssertionError("Timed out waiting for service state")


@pytest.mark.parametrize("mode", ["restart", "git"])
def test_service_replacement_cancels_manual_exec_preserves_scheduled_exec_and_reloads_crontab(tmp_path, mode):
    root = Path(__file__).resolve().parents[2]
    entry = tmp_path / "entry.py"
    # Use the real runtime with a gate-controlled Task; make each startup slot due immediately.
    entry.write_text(dedent("""\
        import json
        import os
        import sys
        import time
        from datetime import datetime
        from pathlib import Path
        from axonx.app.components.cron import CronComponent
        from axonx.cli.main import main
        from axonx.cli.parser import parse_command, validate_cron_command
        from axonx.daemon.launcher import start
        from axonx.daemon.update import UpdateClient
        from axonx.daemon import update_worker
        from axonx.plugin.catalog import BUILTIN_TASKS
        from axonx.task.builtins.demo import DemoTask, DemoTaskInputParams

        VERSION = Path(__file__).with_name("version.txt").read_text()
        UpdateClient._plan = lambda self, mode: {"cwd": str(Path(__file__).parent), "service_pid": os.getpid()}
        update_worker.__file__ = str(Path(__file__).with_name("updater.py"))

        class Inputs(DemoTaskInputParams):
            marker: str
            gate: str

        class WaitingTask(DemoTask):
            input_cls = Inputs

            def initialize(self):
                super().initialize()
                Path(self.input_params.marker).write_text(json.dumps({"pid": os.getpid(), "version": VERSION}))
                while not Path(self.input_params.gate).exists():
                    time.sleep(0.05)

        BUILTIN_TASKS["waiting"] = WaitingTask
        original_start = CronComponent._start

        async def start_cron(self):
            await original_start(self)
            self._next = dict.fromkeys(self._next, datetime.now(self.timezone))

        CronComponent._start = start_cron
        if sys.argv[1] == "start":
            command, _ = parse_command(sys.argv[1:])
            code = start(command.arguments, command_prefix=(sys.executable, __file__),
                         startup_arguments=sys.argv[1:], validate_command=validate_cron_command)
        else:
            code = main()
        raise SystemExit(code)
        """))
    (tmp_path / "updater.py").write_text(dedent("""\
        import json
        import os
        import sys
        from pathlib import Path

        record_path = Path(sys.argv[1])
        plan = json.loads(record_path.with_name("plan.json").read_text())
        try:
            os.kill(plan["service_pid"], 0)
        except ProcessLookupError:
            pass
        else:
            raise RuntimeError("The old service is still running during update")
        root = Path(plan["cwd"])
        os.kill(json.loads((root / "scheduled.json").read_text())["pid"], 0)
        (root / "version.txt").write_text("new")
        record = json.loads(record_path.read_text())
        record["phase"] = "starting"
        record_path.write_text(json.dumps(record))
        """))
    (tmp_path / "version.txt").write_text("old")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    defaults = resolve_app_config(log_config=False)
    workspace = tmp_path / "workspace"
    config = {
        "workspace_dir": str(workspace),
        "log_dir": str(tmp_path / "logs"),
        "log_to_console": False,
        "log_to_file": False,
        "enable_logo": False,
        "components": {"updater": defaults["components"]["updater"]},
        "jobs": {name: defaults["jobs"][name] for name in ("cli", "restart_service", "update_from_git")},
        "service": {
            "backend": "http",
            "host": "127.0.0.1",
            "port": port,
            "token": "test-token",
            "web_enabled": False,
            "cleanup_timeout": 1,
        },
    }
    configuration, crontab = tmp_path / "app.yaml", tmp_path / "commands.cron"
    configuration.write_text(yaml.safe_dump(config))
    scheduled, manual, fresh = (tmp_path / f"{name}.json" for name in ("scheduled", "manual", "fresh"))
    scheduled_gate, fresh_gate = tmp_path / "release-scheduled", tmp_path / "release-fresh"
    crontab.write_text(
        f"* * * * * axonx exec --task waiting --task-name scheduled --x 1 --y 2 "
        f"--marker {scheduled} --gate {scheduled_gate}\n"
    )
    directory = runtime_directory(str(workspace), "127.0.0.1", port, tmp_path)
    environment = {key: value for key, value in os.environ.items() if not key.startswith("AXONX_DAEMON_")}
    environment["PYTHONPATH"] = str(root)
    with (
        (tmp_path / "daemon.log").open("w+") as output,
        subprocess.Popen(
            [sys.executable, str(entry), "start", "--config", str(configuration), "--cron", str(crontab)],
            cwd=tmp_path,
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
        ) as process,
    ):
        owned = []
        try:

            def state():
                return json.loads((directory / "processes.json").read_text())

            first = eventually(lambda: (value := state())["ready"] and value)
            old_task = eventually(lambda: json.loads(scheduled.read_text()))
            assert old_task["version"] == "old"
            assert psutil.Process(old_task["pid"]).ppid() == process.pid
            assert "cron" not in first
            with (
                httpx.Client(
                    base_url=f"http://127.0.0.1:{port}",
                    headers={"Authorization": "Bearer test-token"},
                    timeout=10,
                    trust_env=False,
                ) as client,
                ThreadPoolExecutor(max_workers=1) as pool,
            ):
                request = pool.submit(
                    client.post,
                    "/jobs/cli",
                    timeout=30,
                    json={
                        "arguments": {
                            "argv": [
                                "exec",
                                "--task",
                                "waiting",
                                "--task-name",
                                "manual",
                                "--x",
                                "3",
                                "--y",
                                "4",
                                "--marker",
                                str(manual),
                                "--gate",
                                str(tmp_path / "never-release"),
                            ]
                        }
                    },
                )
                manual_task = eventually(lambda: json.loads(manual.read_text()))
                manual_process = psutil.Process(manual_task["pid"])
                assert manual_process.ppid() == first["service"]
                crontab.write_text(
                    f"* * * * * axonx exec --task waiting --task-name fresh --x 5 --y 6 "
                    f"--marker {fresh} --gate {fresh_gate}\n"
                )
                if mode == "restart":
                    (tmp_path / "version.txt").write_text("new")
                fresh_gate.touch()
                action = "restart_service" if mode == "restart" else "update_from_git"
                restart = client.post(f"/jobs/{action}", json={"arguments": {}}).json()
                assert restart["success"], restart
                second = eventually(
                    lambda: (value := state())["ready"]
                    and value["service"] != first["service"]
                    and value["phase"] == "running"
                    and value
                )
                assert second["pid"] == first["pid"] == process.pid
                record = json.loads(
                    (directory / "updates" / restart["answer"]["update_id"] / "record.json").read_text()
                )
                assert record["phase"] == "succeeded", record
                assert not manual_process.is_running()
                assert not request.result(timeout=5).json()["success"]
                assert old_task["pid"] in second["tasks"]
                assert psutil.Process(old_task["pid"]).is_running()
                assert eventually(lambda: json.loads(fresh.read_text()))["version"] == "new"
                scheduled_gate.touch()
                metadata = task_path(workspace, "base#waiting#scheduled") / "metadata.json"
                result = eventually(
                    lambda: (value := json.loads(metadata.read_text()))["state"] == "succeeded" and value
                )
                assert result["output_params"]["result"] == 3
                eventually(lambda: old_task["pid"] not in state()["tasks"])
        finally:
            owned = psutil.Process(process.pid).children(recursive=True) if process.poll() is None else owned
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            for child in owned:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            psutil.wait_procs(owned, timeout=5)
