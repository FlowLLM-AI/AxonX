"""Verify deployment stops only the selected, locked daemon before source changes."""

import fcntl
import json
import subprocess
import sys
import time
from unittest.mock import Mock

import psutil
import pytest

from scripts import stop_daemon as deploy


def test_unlocked_stale_state_does_not_select_a_process(tmp_path, monkeypatch):
    (tmp_path / "daemon.lock").touch()
    (tmp_path / "processes.json").write_text('{"pid": 123}')
    lookup = Mock()
    monkeypatch.setattr(deploy.psutil, "Process", lookup)
    deploy.stop_daemon(tmp_path, 1)
    lookup.assert_not_called()


@pytest.fixture
def running_daemon(tmp_path, monkeypatch):
    (tmp_path / "daemon.lock").touch()
    (tmp_path / "processes.json").write_text(json.dumps({"pid": 123, "service": 456}))
    lock = (tmp_path / "daemon.lock").open("r+b")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    daemon, service = Mock(pid=123), Mock(pid=456)
    daemon.cmdline.return_value = [
        "/venv/bin/python",
        "-S",
        str(tmp_path / "supervisor.py"),
        str(tmp_path / "plan.json"),
        "7",
    ]
    daemon.wait.side_effect = lambda **_: fcntl.flock(lock, fcntl.LOCK_UN)
    service.ppid.return_value = daemon.pid
    service.is_running.return_value = False
    monkeypatch.setattr(deploy.psutil, "Process", lambda pid: {123: daemon, 456: service}[pid])
    try:
        yield daemon, service
    finally:
        lock.close()


@pytest.mark.parametrize("private_loader", [False, True])
def test_verified_daemon_shutdown_releases_lock_without_killing_service_directly(
    tmp_path, running_daemon, private_loader
):
    daemon, service = running_daemon
    if private_loader:
        daemon.cmdline.return_value = [
            "/runtime/ld-linux-x86-64.so.2",
            "--library-path",
            "/runtime/lib:/venv/lib",
            "--argv0",
            "/launchers/python",
            *daemon.cmdline.return_value,
        ]
    deploy.stop_daemon(tmp_path, 4)
    daemon.terminate.assert_called_once_with()
    daemon.wait.assert_called_once_with(timeout=4)
    service.terminate.assert_not_called()


@pytest.mark.parametrize("mismatch", ["command", "parent", "argument"])
def test_unrelated_process_or_service_is_never_signalled(tmp_path, running_daemon, mismatch):
    daemon, service = running_daemon
    if mismatch == "command":
        daemon.cmdline.return_value = ["python", "unrelated.py"]
    elif mismatch == "argument":
        daemon.cmdline.return_value.append("unrelated.py")
    else:
        service.ppid.return_value = 999
    with pytest.raises(RuntimeError, match="nothing was stopped"):
        deploy.stop_daemon(tmp_path, 1)
    daemon.terminate.assert_not_called()
    service.terminate.assert_not_called()


def test_shutdown_timeout_aborts_deployment(tmp_path, running_daemon):
    daemon, _service = running_daemon
    daemon.wait.side_effect = psutil.TimeoutExpired(1)
    with pytest.raises(psutil.TimeoutExpired):
        deploy.stop_daemon(tmp_path, 1)


def test_surviving_service_aborts_deployment(tmp_path, running_daemon):
    _daemon, service = running_daemon
    service.is_running.return_value = True
    service.status.return_value = psutil.STATUS_RUNNING
    with pytest.raises(RuntimeError, match="still running"):
        deploy.stop_daemon(tmp_path, 1)


def test_real_daemon_and_service_exit_before_deployment_continues(tmp_path):
    script = tmp_path / "supervisor.py"
    plan = tmp_path / "plan.json"
    plan.write_text("{}")
    script.write_text(
        "import fcntl, json, os, signal, subprocess, sys, time\n"
        "from pathlib import Path\n"
        "root = Path(__file__).parent\n"
        "lock = (root / 'daemon.lock').open('a+b')\n"
        "fcntl.flock(lock, fcntl.LOCK_EX)\n"
        "service = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "stopping = False\n"
        "def stop(*args):\n"
        "    global stopping\n"
        "    stopping = True\n"
        "signal.signal(signal.SIGTERM, stop)\n"
        "(root / 'processes.json').write_text(json.dumps({'pid': os.getpid(), 'service': service.pid}))\n"
        "try:\n"
        "    while not stopping: time.sleep(0.01)\n"
        "finally:\n"
        "    service.terminate()\n"
        "    service.wait(timeout=5)\n"
    )
    with subprocess.Popen([sys.executable, "-S", str(script), str(plan), "7"]) as process:
        try:
            deadline = time.monotonic() + 5
            while not (tmp_path / "processes.json").exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    pytest.fail("Deployment test daemon did not start")
                time.sleep(0.01)
            state = json.loads((tmp_path / "processes.json").read_text())
            service = psutil.Process(state["service"])
            deploy.stop_daemon(tmp_path, 5)
            assert not service.is_running()
            assert process.wait(timeout=5) == 0
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)


def test_application_options_select_the_configured_daemon(tmp_path, monkeypatch):
    path = tmp_path / "server.json"
    path.write_text(
        json.dumps(
            {
                "workspace_dir": str(tmp_path / "workspace"),
                "service": {"backend": "http"},
            }
        )
    )
    stop = Mock()
    monkeypatch.setattr(deploy, "load_env", lambda: {})
    monkeypatch.setattr(deploy, "stop_daemon", stop)
    deploy.main(["--config", str(path), "--service.host", "127.0.0.1", "--service.port", "2024"])
    expected = deploy.runtime_directory(str(tmp_path / "workspace"), "127.0.0.1", 2024, deploy.Path.cwd())
    stop.assert_called_once_with(expected, 25)
