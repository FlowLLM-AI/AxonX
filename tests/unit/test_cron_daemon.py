"""Exercise application scheduling and daemon-owned one-shot processes."""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from axonx.app import crontabs
from axonx.app.core.application import Application
from axonx.app.crontabs import load_crontab, parse_crontab
from axonx.cli.parser import validate_cron_command
from axonx.daemon.worker import Supervisor


def test_cron_parser_preserves_argv_without_executing_a_shell():
    entry = parse_crontab('* * * * * axonx exec --task demo --message "a b"')[0]
    assert entry.command == ("axonx", "exec", "--task", "demo", "--message", "a b")


def test_cron_preserves_commands_without_interpreting_their_options():
    entry = parse_crontab('* * * * * worker --message "a b" --value true --value 01\n')[0]
    assert entry.command == ("worker", "--message", "a b", "--value", "true", "--value", "01")


@pytest.mark.parametrize("command", ['""', 'worker "unterminated'])
def test_cron_rejects_invalid_command_boundaries(command):
    with pytest.raises(ValueError, match="Cron line 2:"):
        parse_crontab(f"* * * * * worker\n* * * * * {command}")


def cron_app(tmp_path, launch):
    return Application(
        workspace_dir=str(tmp_path),
        timezone="UTC",
        log_to_console=False,
        log_to_file=False,
        components={
            "cron": {
                "default": {
                    "backend": "cron",
                    "source": str(tmp_path / "commands.cron"),
                    "launch": launch,
                    "validate_command": validate_cron_command,
                }
            }
        },
    )


async def test_cron_advances_a_slot_even_when_launch_fails(tmp_path):
    path = tmp_path / "commands.cron"
    path.write_text("* * * * * axonx exec --task demo\n")
    launches = []

    async def launch(entry):
        launches.append(entry)
        raise OSError("worker unavailable")

    app = cron_app(tmp_path, launch)
    scheduler = app.context.components["cron"]["default"]
    now = datetime(2026, 10, 26, 12, 0, tzinfo=ZoneInfo("UTC"))
    scheduler._next = {1: now}
    await scheduler._tick(now)
    await scheduler._tick(now + timedelta(seconds=1))
    assert len(launches) == 1
    app.request_shutdown()
    await scheduler._tick(now + timedelta(minutes=1))
    assert len(launches) == 1


def test_bundled_crontab_is_next_to_application_config():
    path, entries = load_crontab("research", validate_cron_command)
    assert path.parent == Path(crontabs.__file__).resolve().parent
    assert path.parent.parent.name == "app"
    assert not entries


@pytest.mark.parametrize("state", ["stopping", "maintenance"])
async def test_cron_stops_new_launches_during_an_awaited_request(tmp_path, state):
    (tmp_path / "commands.cron").write_text("* * * * * axonx exec --task demo\n* * * * * axonx exec --task demo\n")
    entered, release = asyncio.Event(), asyncio.Event()
    launched = []

    async def launch(entry):
        launched.append(entry.line)
        entered.set()
        await release.wait()

    app = cron_app(tmp_path, launch)
    scheduler = app.context.components["cron"]["default"]
    now = datetime.now(ZoneInfo("UTC"))
    scheduler._next = {entry.line: now for entry in scheduler.entries}
    tick = asyncio.create_task(scheduler._tick(now))
    await asyncio.wait_for(entered.wait(), 1)
    app.context.metadata[state] = True
    release.set()
    await asyncio.wait_for(tick, 1)
    assert launched == [1]


async def test_application_restart_rereads_crontab_without_replaying_missed_slots(tmp_path):
    path = tmp_path / "commands.cron"
    path.write_text("* * * * * axonx exec --task demo --x 1\n")
    launched = []

    async def launch(entry):
        launched.append(entry)

    first = cron_app(tmp_path, launch)
    async with first:
        scheduler = first.context.components["cron"]["default"]
        assert scheduler._runner is not None
        assert all(value > datetime.now(scheduler.timezone) for value in scheduler._next.values())
    assert scheduler._runner is None
    path.write_text("0 * * * * axonx exec --task demo --x 2\n")
    async with cron_app(tmp_path, launch) as second:
        assert second.context.components["cron"]["default"].entries[0].command[-1] == "2"
    assert not launched


def test_daemon_executes_an_injected_command_without_interpreting_tasks(tmp_path):
    supervisor = Supervisor({"directory": str(tmp_path), "stop_timeout": 1})
    supervisor.ready = True
    output = tmp_path / "result.txt"
    command = [sys.executable, "-c", f"from pathlib import Path; Path({str(output)!r}).write_text('done')"]
    result = supervisor._exec(
        {
            "command": command,
            "cwd": str(tmp_path),
            "environment": dict(os.environ),
            "log_file": str(tmp_path / "command.log"),
        }
    )
    child = supervisor.tasks[result["pid"]]
    try:
        assert child.wait(timeout=5) == 0
        assert output.read_text() == "done"
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
