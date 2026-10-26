"""Validate the thin CLI through real, independently supervised local workers."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from time import monotonic, sleep

import httpx
import psutil
import yaml

from axonx.app.config.resolver import resolve_app_config
from axonx.daemon.client import runtime_directory
from axonx.daemon.update import UpdateClient
from axonx.daemon import client as daemon


def test_cli_validates_the_complete_crontab_before_launching_workers(tmp_path, monkeypatch, capsys):
    from axonx.cli.main import main
    from axonx.daemon import launcher

    monkeypatch.delenv(daemon.ROLE, raising=False)
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


def test_cli_start_supervises_app_and_cron_and_injects_the_command_driver(tmp_path):
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
    crontab.write_text("# Start the independent Cron worker without firing tasks.\n")
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
                            if state.get("cron") and health["answer"]["running"]:
                                children = [psutil.Process(state[name]) for name in ("service", "cron")]
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

    monkeypatch.delenv(daemon.ROLE, raising=False)
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
