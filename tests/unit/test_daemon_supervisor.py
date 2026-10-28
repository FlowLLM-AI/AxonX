"""Verify daemon failure recovery and cleanup of owned process groups."""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent
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


@pytest.mark.parametrize("blocked", [None, "service", "update"])
def test_interrupt_with_a_blocked_console_stops_service_and_preserves_scheduled_work(supervisor, tmp_path, blocked):
    marker = tmp_path / "started"
    service = (
        "import signal, time; from pathlib import Path; "
        f"signal.signal(signal.SIGTERM, signal.SIG_IGN if {blocked == 'service'!r} else signal.SIG_DFL); "
        "print('服务日志' * 262144); "
        f"Path({str(marker)!r}).touch(); time.sleep(60)"
    )
    runner = dedent("""\
        import json
        import sys
        from pathlib import Path

        sys.path.insert(0, sys.argv[1])
        import supervisor

        run = supervisor.Supervisor.run

        def with_scheduled_work(owner):
            task = owner._spawn([sys.executable, '-c', 'import time; time.sleep(60)'],
                                owner.plan['cwd'], owner.plan['environment'], owner.directory / 'scheduled.log')
            owner.tasks[task.pid] = task
            if owner.plan['blocked_update']:
                command = ("import signal, time; from pathlib import Path; "
                           "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                           "Path('updating').touch(); time.sleep(60)")
                owner.update = owner._spawn([sys.executable, '-c', command], owner.plan['cwd'],
                                            owner.plan['environment'], owner.directory / 'update.log')
                (owner.directory / 'updater.pid').write_text(str(owner.update.pid))
            run(owner)

        supervisor.Supervisor.run = with_scheduled_work
        sys.argv = ['supervisor.py', sys.argv[2], '0']
        supervisor.main()
        """)
    state = {}
    with TemporaryDirectory(prefix="axonx-test-", dir="/tmp") as sockets:
        plan = {
            **supervisor.plan,
            "environment": dict(os.environ),
            "command": [sys.executable, "-c", service],
            "socket": str(Path(sockets) / "daemon.sock"),
            "stop_timeout": 60,
            "blocked_update": blocked == "update",
        }
        path = tmp_path / "plan.json"
        path.write_text(json.dumps(plan))
        with subprocess.Popen(
            [sys.executable, "-S", "-c", runner, str(Path(update.__file__).parent), str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        ) as process:
            try:
                deadline = monotonic() + 5
                while monotonic() < deadline and process.poll() is None:
                    if (tmp_path / "processes.json").exists():
                        state = json.loads((tmp_path / "processes.json").read_text())
                        if (
                            state["service"]
                            and marker.exists()
                            and (blocked != "update" or (tmp_path / "updating").exists())
                        ):
                            break
                    sleep(0.02)
                assert marker.exists(), "Service blocked on console output"
                if blocked == "update":
                    assert (tmp_path / "updating").exists()
                # Leave stdout unread to simulate a terminal/pipe that has stopped consuming logs.
                started = monotonic()
                os.killpg(process.pid, signal.SIGINT)
                sleep(0.1)
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
                assert process.wait(timeout=6) == (130 if blocked else 0)
                assert monotonic() - started < 5.5
                wait_stopped(state["service"])
                assert len(state["tasks"]) == 1
                assert not stopped(state["tasks"][0])
                assert "服务日志" * 262144 in (tmp_path / "service.log").read_text()
                if not blocked:
                    assert not Path(plan["socket"]).exists()
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                for pid in [state.get("service"), *state.get("tasks", [])]:
                    if pid:
                        update.signal_group(pid)
                if (tmp_path / "updater.pid").exists():
                    updater = int((tmp_path / "updater.pid").read_text())
                    if process.returncode == 130:
                        assert stopped(updater)
                    update.signal_group(updater)


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
