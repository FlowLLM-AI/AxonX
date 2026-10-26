"""Exercise scheduling and process supervision without loading Task execution."""

from datetime import datetime, timedelta
import os
import sys
from zoneinfo import ZoneInfo

import pytest

from axonx.cron.parser import parse_crontab
from axonx.cron.scheduler import CronScheduler
from axonx.daemon.worker import Supervisor


def test_cron_parser_preserves_argv_without_executing_a_shell():
    entry = parse_crontab('* * * * * axonx exec --task demo --message "a b"')[0]
    assert entry.command == ("axonx", "exec", "--task", "demo", "--message", "a b")


def test_cron_preserves_commands_without_interpreting_their_options(tmp_path):
    path = tmp_path / "commands.cron"
    path.write_text('* * * * * worker --message "a b" --value true --value 01\n')
    scheduler = CronScheduler(path, timezone="UTC", launch=lambda _: None)
    assert scheduler.entries[0].command == ("worker", "--message", "a b", "--value", "true", "--value", "01")


@pytest.mark.parametrize("command", ['""', 'worker "unterminated'])
def test_cron_rejects_invalid_command_boundaries(command):
    with pytest.raises(ValueError, match="Cron line 2:"):
        parse_crontab(f"* * * * * worker\n* * * * * {command}")


def test_cron_advances_a_slot_even_when_launch_fails(tmp_path):
    path = tmp_path / "commands.cron"
    path.write_text("* * * * * axonx exec --task demo\n")
    launches = []

    def launch(entry):
        launches.append(entry)
        raise OSError("worker unavailable")

    scheduler = CronScheduler(path, timezone="UTC", launch=launch)
    now = datetime(2026, 10, 26, 12, 0, tzinfo=ZoneInfo("UTC"))
    scheduler._next = {1: now}
    scheduler._tick(now)
    scheduler._tick(now + timedelta(seconds=1))
    assert len(launches) == 1
    scheduler.stop()
    scheduler._tick(now + timedelta(minutes=1))
    assert len(launches) == 1


def test_daemon_executes_an_injected_command_without_interpreting_tasks(tmp_path):
    supervisor = Supervisor({"directory": str(tmp_path), "stop_timeout": 1})
    supervisor.ready.add("cron")
    supervisor.execution = {"log_dir": str(tmp_path), "cwd": str(tmp_path), "environment": dict(os.environ)}
    output = tmp_path / "result.txt"
    command = [sys.executable, "-c", f"from pathlib import Path; Path({str(output)!r}).write_text('done')"]
    result = supervisor._exec({"command": command, "line": 1})
    child = supervisor.tasks[result["pid"]]
    try:
        assert child.wait(timeout=5) == 0
        assert output.read_text() == "done"
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
