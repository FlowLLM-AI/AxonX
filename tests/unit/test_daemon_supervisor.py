"""Verify daemon failure recovery and cleanup of owned process groups."""

import json
import os
import subprocess
import sys
from time import monotonic, sleep

import psutil
import pytest

from axonx.daemon import update
from axonx.daemon.client import DaemonClient
from axonx.daemon.supervisor import Supervisor


def stopped(pid):
    try:
        return not psutil.Process(pid).is_running() or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return True


def wait_stopped(pid):
    deadline = monotonic() + 5
    while monotonic() < deadline:
        if stopped(pid):
            return
        sleep(0.02)
    raise AssertionError(f"Owned process {pid} survived cleanup")


@pytest.fixture
def supervisor(tmp_path):
    return Supervisor(
        {
            "directory": str(tmp_path),
            "cwd": str(tmp_path),
            "python": sys.executable,
            "environment": {},
            "stop_timeout": 1,
        }
    )


def prepare(supervisor, worker=None):
    return supervisor._prepare(
        {"mode": "git", "worker": str(worker or update.__file__), "plan": {}, "versions": {"axonx": "before"}}
    )


def test_crashed_service_descendants_are_cleaned_up_before_restart(supervisor, tmp_path):
    marker = tmp_path / "child.json"
    command = (
        "import json, subprocess, sys; from pathlib import Path; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        f"Path({str(marker)!r}).write_text(json.dumps(child.pid))"
    )
    child = supervisor._spawn(
        [sys.executable, "-c", command], str(tmp_path), dict(os.environ), tmp_path / "service.log"
    )
    supervisor.service = child
    try:
        assert child.wait(timeout=5) == 0
        descendant = json.loads(marker.read_text())
        supervisor._poll_service(monotonic())
        wait_stopped(descendant)
        assert supervisor.service is None
        assert supervisor.retry > monotonic()
    finally:
        update.signal_group(child.pid)
        child.wait(timeout=5)


def test_expired_update_releases_admission_and_invalidates_the_old_service(supervisor):
    supervisor.token, supervisor.ready = "old-token", True
    prepare(supervisor)
    with pytest.raises(RuntimeError, match="already pending"):
        prepare(supervisor)
    with pytest.raises(RuntimeError, match="paused"):
        supervisor._exec({})
    with pytest.raises(ValueError, match="awaiting commit"):
        supervisor.handle({"action": "commit_update", "token": "old-token", "update_id": "wrong"})
    supervisor.commit_deadline = 0
    supervisor.retry = float("inf")
    supervisor._poll()
    assert supervisor.pending is None
    assert supervisor.phase == "running"
    assert not supervisor.ready
    with pytest.raises(ValueError, match="token"):
        supervisor.handle({"action": "ready", "token": "old-token"})
    record = next((supervisor.directory / "updates").glob("*/record.json"))
    assert "did not commit" in json.loads(record.read_text())["error"]


@pytest.mark.parametrize("message", [None, [], "ready", {"token": "wrong"}])
def test_invalid_control_messages_are_rejected(supervisor, message):
    supervisor.token = "valid-token"
    with pytest.raises(ValueError):
        supervisor.handle(message)


def test_updater_crash_is_logged_and_stays_failed_after_service_recovers(supervisor, tmp_path):
    worker = tmp_path / "broken.py"
    worker.write_text("raise RuntimeError('broken updater')\n")
    record = prepare(supervisor, worker)
    supervisor.token = "old-token"
    supervisor.handle({"action": "commit_update", "token": "old-token", "update_id": record["update_id"]})
    supervisor._poll_update()
    try:
        assert supervisor.update.wait(timeout=5) != 0
        supervisor._poll_update()
        assert supervisor.phase == "starting"
        supervisor.token = "new-token"
        supervisor.handle({"action": "ready", "token": "new-token", "stop_timeout": 1, "versions": {"axonx": "after"}})
        supervisor._settle()
        result = DaemonClient(tmp_path, tmp_path, "").status(record["update_id"])
        assert result["record"]["phase"] == "failed"
        assert "Updater exited" in result["record"]["error"]
        assert result["record"]["after"] == {"axonx": "after"}
        assert "broken updater" in result["log"]
    finally:
        if supervisor.update is not None:
            supervisor.update.kill()
            supervisor.update.wait(timeout=5)


def test_update_timeout_reaps_descendants_and_preserves_command_output(tmp_path):
    marker = tmp_path / "processes.json"
    command = (
        "import json, os, subprocess, sys, time; from pathlib import Path; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        f"Path({str(marker)!r}).write_text(json.dumps([os.getpid(), child.pid])); "
        "print('command started', flush=True); time.sleep(60)"
    )
    with (tmp_path / "command.log").open("w+") as log:
        try:
            with pytest.raises(subprocess.TimeoutExpired):
                update.run_command([sys.executable, "-c", command], str(tmp_path), log, timeout=2)
            for pid in json.loads(marker.read_text()):
                wait_stopped(pid)
            log.seek(0)
            assert "command started" in log.read()
        finally:
            if marker.exists():
                update.signal_group(json.loads(marker.read_text())[0])


def test_update_status_uses_the_daemon_directory_and_bounds_log_reads(tmp_path, monkeypatch):
    owner = tmp_path / "owner"
    monkeypatch.setenv("AXONX_DAEMON_DIRECTORY", str(owner))
    client = DaemonClient(tmp_path / "different-config", tmp_path, "")
    record = owner / "updates" / ("a" * 32) / "record.json"
    record.parent.mkdir(parents=True)
    update.save(record, {"phase": "succeeded"})
    record.with_name("update.log").write_bytes(b"old" + b"x" * 65536)
    result = client.status()
    assert result["record"]["phase"] == "succeeded"
    assert result["log"] == "x" * 65536
    with pytest.raises(ValueError, match="Invalid update_id"):
        client.status("../record")
