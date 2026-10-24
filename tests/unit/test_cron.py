"""Crontab lookup, safe command parsing and independent exec lifecycle."""

from datetime import datetime, timedelta
from importlib.metadata import EntryPoint
from zoneinfo import ZoneInfo

import pytest

from axonx.config import ConfigResolver
from axonx.config.locator import locate_file
from axonx.app.core import Application
from axonx.cron.parser import parse_crontab
from axonx.cron.scheduler import CronScheduler


def scheduler(tmp_path, text="* * * * * axonx exec --task demo --task-name cron-demo --x 2 --y 3"):
    path = tmp_path / "tasks.cron"
    path.write_text(text)
    return CronScheduler(
        path,
        workspace_dir=str(tmp_path / "workspace"),
        log_dir=str(tmp_path / "logs"),
        timezone="Asia/Shanghai",
        environment={"CRON_TEST_ENV": "present"},
        launch=lambda entry: None,
    )


def test_parser_preserves_quotes_hashes_and_literal_shell_expansions():
    entries = parse_crontab("""
# Whole-line comment
0 16 * * 1-5 axonx exec --task train --source-tasks "etl#data#daily" --json '{"text":"a b # $HOME $(echo x)"}'
*/10 * * * * axonx exec --task demo --x 1 --y 2
""")
    assert [entry.line for entry in entries] == [3, 4]
    assert entries[0].arguments == (
        "--task",
        "train",
        "--source-tasks",
        "etl#data#daily",
        "--json",
        '{"text":"a b # $HOME $(echo x)"}',
    )
    assert parse_crontab(" \n # empty\n") == ()


@pytest.mark.parametrize(
    "text",
    [
        "@daily axonx exec --task demo",
        "60 * * * * axonx exec --task demo",
        "0 0 * * * 0 axonx exec --task demo",
        "* * * * * root axonx exec --task demo",
        "* * * * * python script.py",
        "* * * * * axonx start",
        "* * * * * axonx exec",
        "* * * * * axonx exec --task demo --target remote:1024",
        "* * * * * axonx exec --task demo --stream true",
        "* * * * * axonx exec --task demo --task other",
        "* * * * * axonx exec --task demo | cat",
        "* * * * * axonx exec --task demo > out",
        "* * * * * axonx exec --task demo && touch marker",
        '* * * * * axonx exec --task "demo',
        "FOO=bar",
    ],
)
def test_invalid_entry_rejects_the_complete_file_with_its_line(text):
    with pytest.raises(ValueError, match="Cron line 3:"):
        parse_crontab("* * * * * axonx exec --task demo\n# comment\n" + text)


def test_shared_locator_keeps_names_paths_extension_priority_and_provider_conflicts(tmp_path, monkeypatch):
    (tmp_path / "research.cron").write_text("# empty")
    monkeypatch.chdir(tmp_path)
    options = {"directory": tmp_path, "extensions": (".cron",), "group": "axonx.crons", "label": "Cron"}
    assert locate_file("research", **options) == tmp_path / "research.cron"
    assert locate_file("./research.cron", **options).resolve() == tmp_path / "research.cron"
    with pytest.raises(FileNotFoundError, match="Available: research"):
        locate_file("missing", **options)
    monkeypatch.setattr(
        "axonx.config.locator.find_entry_points",
        lambda *_: [EntryPoint(name="research", value="axonx.cron", group="axonx.crons")],
    )
    with pytest.raises(ValueError, match="both AxonX and an installed distribution"):
        locate_file("research", **options)
    (tmp_path / "app.json").write_text('{"value":"json"}')
    (tmp_path / "app.yaml").write_text("value: yaml")
    monkeypatch.setattr("axonx.config.locator.find_entry_points", lambda *_: [])
    assert ConfigResolver(tmp_path).load("app") == {"value": "yaml"}


def test_cron_contributions_are_loaded_from_their_own_entry_point_group(tmp_path, monkeypatch):
    seen = []

    def entries(group, name):
        seen.append((group, name))
        return [EntryPoint(name=name, value="axonx.cron:research", group=group)]

    monkeypatch.setattr("axonx.config.locator.find_entry_points", entries)
    path = locate_file("plugin-research", directory=tmp_path, extensions=(".cron",), group="axonx.crons", label="Cron")
    assert path.name == "research.cron"
    assert seen == [("axonx.crons", "plugin-research")]


@pytest.mark.parametrize("now,expected", [("2026-03-08T01:30:00", 3600), ("2026-11-01T00:30:00", 10800)])
def test_next_occurrence_respects_timezone_and_dst(now, expected):
    current = datetime.fromisoformat(now).replace(tzinfo=ZoneInfo("America/New_York"))
    expression = "30 3 * * *" if expected == 3600 else "30 2 * * *"
    entry = parse_crontab(expression + " axonx exec --task demo")[0]
    assert entry.next_after(current).timestamp() - current.timestamp() == expected


async def test_tick_skips_missed_slots_and_failed_launch_does_not_block_other_entries(tmp_path, monkeypatch):
    cron = scheduler(tmp_path, "* * * * * axonx exec --task first\n* * * * * axonx exec --task second")
    await cron.start()
    now = datetime.now(cron.timezone)
    cron._next = {entry.line: now - timedelta(minutes=20) for entry in cron.entries}
    launched = []

    def launch(entry):
        launched.append(entry.line)
        if entry.line == 1:
            raise OSError("spawn failed")

    monkeypatch.setattr(cron, "_launch", launch)
    try:
        cron._tick(now)
        cron._tick(now)
        assert launched == [1, 2]
        assert all(date > now for date in cron._next.values())
        cron.stop()
        cron._tick(now + timedelta(hours=1))
        assert launched == [1, 2]
    finally:
        await cron.close()


async def test_embedded_application_has_no_cron_process_and_rejects_old_schedules(tmp_path):
    async with Application(
        workspace_dir=str(tmp_path), cron="research", log_to_console=False, log_to_file=False
    ) as app:
        assert not hasattr(app.context, "cron")
    with pytest.raises(ValueError, match="schedules"):
        Application(schedules={})


def test_start_passes_original_arguments_to_the_daemon(tmp_path, monkeypatch):
    from axonx.cli import main
    from axonx.daemon import client

    config = tmp_path / "app.yaml"
    config.write_text("service: {backend: http}\nlog_to_console: false\nlog_to_file: false\nenable_logo: false\n")
    captured = []
    monkeypatch.setattr(client, "launch", lambda plan, directory: captured.append((plan, directory)))
    monkeypatch.chdir(tmp_path)
    assert main(["start", "--config", str(config), "--cron", "research"]) == 0
    plan, directory = captured[0]
    assert plan["command"][-5:] == ["start", "--config", str(config), "--cron", "research"]
    assert directory.is_relative_to(tmp_path / ".axonx" / "daemon")
