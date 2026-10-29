"""Exercise application scheduling and daemon-owned one-shot processes."""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import yaml

from axonx.app.config.loader import ConfigLoader
from axonx.app.config.models import ApplicationConfig, CronConfig
from axonx.app.core.application import Application
from axonx.cli.parser import parse_command, validate_cron_command
from axonx.daemon.supervisor import Supervisor


def test_cron_config_preserves_argv_without_executing_a_shell():
    command = 'axonx exec --task demo --message "a b; $(touch unwanted)"'
    entry = CronConfig(expression="* * * * *", command=command)
    assert entry.argv == ("axonx", "exec", "--task", "demo", "--message", "a b; $(touch unwanted)")
    assert entry.model_dump(mode="json") == {"expression": "* * * * *", "command": command}


def test_structured_cron_commands_share_yaml_arguments_without_shell_expansion():
    values = yaml.safe_load("""
cron:
  - expression: "0 9 * * 1-5"
    command: [axonx, exec, --task, first, --models, &models {"0945": [{task_name: "a b; $(touch unwanted)"}]}]
  - expression: "30 21 * * 1-5"
    command: [axonx, exec, --task, second, --models, *models]
""")
    config = ApplicationConfig.model_validate(values)
    arguments = []
    for entry in config.cron:
        validate_cron_command(entry.argv)
        command, _ = parse_command(entry.argv[1:])
        arguments.append(command.arguments)
        assert isinstance(entry.command, str)
    assert [entry["task"] for entry in arguments] == ["first", "second"]
    assert arguments[0]["models"] == arguments[1]["models"] == {"0945": [{"task_name": "a b; $(touch unwanted)"}]}


def test_cron_preserves_commands_without_interpreting_their_options():
    entry = CronConfig(expression="* * * * *", command='worker --message "a b" --value true --value 01')
    assert entry.argv == (
        "worker",
        "--message",
        "a b",
        "--value",
        "true",
        "--value",
        "01",
    )


@pytest.mark.parametrize("command", ["", " ", '""', 'worker "unterminated'])
def test_cron_rejects_invalid_command_boundaries(command):
    with pytest.raises(ValueError, match=r"cron\.1"):
        ApplicationConfig(
            cron=[
                {"expression": "* * * * *", "command": "axonx exec --task demo"},
                {"expression": "* * * * *", "command": command},
            ]
        )


@pytest.mark.parametrize("expression", ["@daily", "0 16 * *", "0 16 * * * *", "0 25 * * *", "*/0 * * * *"])
def test_cron_rejects_invalid_or_non_five_field_expressions(expression):
    with pytest.raises(ValueError, match=r"cron\.0\.expression"):
        ApplicationConfig(cron=[{"expression": expression, "command": "axonx exec --task demo"}])


@pytest.mark.parametrize("override", [None, [], [{"expression": "0 16 * * 1-5", "command": "${AXONX_TEST_COMMAND}"}]])
def test_cron_shares_config_inheritance_environment_and_list_replacement(tmp_path, monkeypatch, override):
    monkeypatch.setenv("AXONX_TEST_COMMAND", "axonx exec --task demo --x 3")
    base = [{"expression": "* * * * *", "command": f"axonx exec --task demo --x {value}"} for value in (1, 2)]
    (tmp_path / "base.yaml").write_text(yaml.safe_dump({"cron": base}))
    values = {"extends": "base.yaml"}
    if override is not None:
        values["cron"] = override
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump(values))
    config = ApplicationConfig(**ConfigLoader().resolve(config=str(path), log_config=False))
    expected = ["1", "2"] if override is None else (["3"] if override else [])
    assert [entry.argv[-1] for entry in config.cron] == expected


def cron_app(tmp_path, launch, entries=None):
    return Application(
        launch_scheduled=launch,
        workspace_dir=str(tmp_path),
        timezone="UTC",
        log_to_console=False,
        log_to_file=False,
        cron=entries if entries is not None else [{"expression": "* * * * *", "command": "axonx exec --task demo"}],
    )


def test_cron_requires_a_launcher_and_empty_schedules_create_no_component(tmp_path):
    with pytest.raises(ValueError, match="scheduled command launcher"):
        cron_app(tmp_path, None)
    assert not cron_app(tmp_path, None, []).context.components


async def test_cron_requires_an_explicit_timezone_when_ticking(tmp_path):
    async def launch(_index, _entry):
        pytest.fail("A naive timestamp must be rejected before any launch")

    scheduler = cron_app(tmp_path, launch).context.components["cron"]["default"]
    with pytest.raises(ValueError, match="timezone-aware"):
        await scheduler.tick(datetime(2026, 10, 26, 12, 0))


@pytest.mark.parametrize("error_type", [OSError, RuntimeError, ValueError, TimeoutError])
async def test_cron_advances_failed_slots_and_continues_other_launches(tmp_path, error_type):
    launches = []

    async def launch(_index, entry):
        launches.append(entry)
        raise error_type("worker unavailable")

    entries = [{"expression": "* * * * *", "command": f"worker --value {value}"} for value in (1, 2)]
    app = cron_app(tmp_path, launch, entries)
    scheduler = app.context.components["cron"]["default"]
    now = datetime(2026, 10, 26, 12, 0, tzinfo=ZoneInfo("UTC"))
    scheduler._next = [now] * len(entries)
    await scheduler.tick(now)
    await scheduler.tick(now + timedelta(seconds=1))
    assert launches == list(scheduler.entries)
    app.request_shutdown()
    await scheduler.tick(now + timedelta(minutes=1))
    assert launches == list(scheduler.entries)


@pytest.mark.parametrize(
    ("expression", "due", "now", "expected"),
    [
        ("* * * * *", "2026-10-26T12:00:00+00:00", "2026-10-26T12:10:00+00:00", "2026-10-26T12:11:00+00:00"),
        ("0 9 * * *", "2026-10-26T09:00:00+00:00", "2026-10-26T17:00:00+08:00", "2026-10-27T09:00:00+00:00"),
    ],
)
async def test_cron_coalesces_missed_slots_in_the_configured_timezone(tmp_path, expression, due, now, expected):
    launched = []

    async def launch(index, _entry):
        launched.append(index)

    app = cron_app(tmp_path, launch, [{"expression": expression, "command": "worker"}])
    scheduler = app.context.components["cron"]["default"]
    scheduler._next = [datetime.fromisoformat(due)]
    now = datetime.fromisoformat(now)
    await scheduler.tick(now)
    await scheduler.tick(now + timedelta(seconds=1))
    assert launched == [0]
    assert scheduler._next == [datetime.fromisoformat(expected)]


async def test_cron_snapshots_entries_against_config_list_mutation(tmp_path):
    launched = []

    async def launch(_index, entry):
        launched.append(entry)

    app = cron_app(tmp_path, launch)
    scheduler = app.context.components["cron"]["default"]
    original_entry = app.app_config.cron[0]
    app.app_config.cron.append(CronConfig(expression="* * * * *", command="other-worker"))
    async with app:
        scheduler._next = [datetime.now(scheduler.timezone)]
        await scheduler.tick(scheduler._next[0])
    assert launched == [original_entry]


async def test_cron_propagates_launch_cancellation_without_replaying_the_slot(tmp_path):
    launched = []

    async def launch(index, _entry):
        launched.append(index)
        raise asyncio.CancelledError

    app = cron_app(tmp_path, launch)
    scheduler = app.context.components["cron"]["default"]
    now = datetime.now(scheduler.timezone)
    scheduler._next = [now]
    with pytest.raises(asyncio.CancelledError):
        await scheduler.tick(now)
    await scheduler.tick(now)
    assert launched == [0]


async def test_cron_clears_failed_runner_state_and_can_restart(tmp_path, monkeypatch):
    async def launch(_index, _entry):
        pass

    async def fail():
        raise RuntimeError("scheduler failed")

    app = cron_app(tmp_path, launch)
    scheduler = app.context.components["cron"]["default"]
    run = scheduler._run
    monkeypatch.setattr(scheduler, "_run", fail)
    await scheduler.start()
    await asyncio.sleep(0)
    with pytest.raises(RuntimeError, match="scheduler failed"):
        await scheduler.close()
    assert scheduler._runner is None
    assert scheduler._next == []
    monkeypatch.setattr(scheduler, "_run", run)
    async with scheduler:
        assert scheduler._runner is not None
        assert scheduler._next


@pytest.mark.parametrize("state", ["stopping", "maintenance"])
async def test_cron_stops_new_launches_during_an_awaited_request(tmp_path, state):
    entered, release = asyncio.Event(), asyncio.Event()
    launched = []

    async def launch(index, _entry):
        launched.append(index)
        entered.set()
        await release.wait()

    app = cron_app(tmp_path, launch, [{"expression": "* * * * *", "command": "axonx exec --task demo"}] * 2)
    scheduler = app.context.components["cron"]["default"]
    now = datetime.now(ZoneInfo("UTC"))
    scheduler._next = [now] * len(scheduler.entries)
    tick = asyncio.create_task(scheduler.tick(now))
    await asyncio.wait_for(entered.wait(), 1)
    app.context.metadata[state] = True
    release.set()
    await asyncio.wait_for(tick, 1)
    assert launched == [0]


async def test_application_restart_rereads_config_without_replaying_missed_slots(
    tmp_path,
):
    path = tmp_path / "app.yaml"
    path.write_text(yaml.safe_dump({"cron": [{"expression": "* * * * *", "command": "axonx exec --task demo --x 1"}]}))
    launched = []

    async def launch(_index, entry):
        launched.append(entry)

    first = cron_app(tmp_path, launch, ConfigLoader().resolve(config=str(path), log_config=False)["cron"])
    async with first:
        scheduler = first.context.components["cron"]["default"]
        assert scheduler._runner is not None
        assert all(value > datetime.now(scheduler.timezone) for value in scheduler._next)
    assert scheduler._runner is None
    assert scheduler._next == []
    path.write_text(yaml.safe_dump({"cron": [{"expression": "0 * * * *", "command": "axonx exec --task demo --x 2"}]}))
    async with cron_app(tmp_path, launch, ConfigLoader().resolve(config=str(path), log_config=False)["cron"]) as second:
        assert second.context.components["cron"]["default"].entries[0].argv[-1] == "2"
    assert not launched


def test_daemon_executes_an_injected_command_without_interpreting_tasks(tmp_path):
    supervisor = Supervisor({"directory": str(tmp_path), "stop_timeout": 1})
    supervisor.ready = True
    output = tmp_path / "result.txt"
    command = [
        sys.executable,
        "-c",
        f"from pathlib import Path; Path({str(output)!r}).write_text('done')",
    ]
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
