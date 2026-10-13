"""Schedule provenance survives worker and child execution and scopes maintenance."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from axonx.components.task_manager.local.manager import LocalTaskManager
from axonx.components.updater.manager import RESPONSE_CALLBACKS
from axonx.config import resolve_app_config
from axonx.core import Application
from axonx.enums import TaskState, TaskType
from axonx.task import BaseCompositeTask
from axonx.task.query.summary import summarize_status
from axonx.task.runtime.executor import TaskCommandExecutor
from axonx.task.runtime.runner import TaskRunner
from axonx.task.source import TASK_SOURCE, TASK_SOURCE_ENV, ScheduleTrigger, TaskSource
from axonx.task.storage.workspace import TaskMetadata, read_task_metadata, task_path


def source(name="daily"):
    return TaskSource(
        kind="submit",
        schedule=ScheduleTrigger(name=name, job="submit", trigger_id="trigger", triggered_at=datetime.now(UTC)),
    )


def application(tmp_path):
    config = resolve_app_config(log_config=False)
    config.update(
        workspace_dir=str(tmp_path / "workspace"),
        log_dir=str(tmp_path / "logs"),
        enable_logo=False,
        log_to_console=False,
        log_to_file=False,
    )
    config["components"] = {
        "task_repository": {"default": {"backend": "local"}},
        "task_manager": {"default": {"backend": "local"}},
        "updater": {"default": {"backend": "local"}},
    }
    config["jobs"] = {
        name: config["jobs"][name] for name in ("submit", "list_schedules", "get_update_status", "version")
    }
    config["schedules"] = {
        "daily": {"job": "submit", "cron": "0 18 * * *", "arguments": {"task": "demo", "x": 1, "y": 2}},
        "heartbeat": {"job": "version", "cron": "0 * * * *"},
    }
    app = Application(**config)
    app.context.service.server = SimpleNamespace(started=True)
    app.context.service.restart_arguments = ["start"]
    return app


@pytest.mark.asyncio
async def test_scheduler_records_queued_worker_source_without_leaking_to_manual_submit(tmp_path, monkeypatch):
    app = application(tmp_path)
    async with app:
        manager = app.context.components["task_manager"]["default"]
        launches = []

        async def spawn(argv, environment, *_):
            launches.append((argv, environment))

        monkeypatch.setattr(manager._supervisor, "spawn", spawn)
        scheduler = app.context.schedulers["daily"]
        await scheduler._trigger()
        await asyncio.gather(*tuple(scheduler._executions))
        queued = (await manager.list_statuses())[0]
        assert queued.source.schedule.name == "daily"
        assert queued.state == TaskState.QUEUED
        assert "source" not in queued.input_params
        assert TASK_SOURCE.get().schedule is None
        for name, value in launches[0][1].items():
            monkeypatch.setenv(name, value)
        completed = (
            TaskCommandExecutor(manager.workspace_path)
            .execute(SimpleNamespace(action="exec", arguments={"task": "demo", **queued.input_params}))
            .status
        )
        assert completed.source == queued.source
        assert completed.state == TaskState.SUCCEEDED
        assert TaskSource.model_validate_json(launches[0][1][TASK_SOURCE_ENV]) == queued.source
        await manager.submit(["--task", "demo", "--x", "2", "--y", "3"])
        assert launches[1][1][TASK_SOURCE_ENV] == TaskSource(kind="submit").model_dump_json()
        schedules = (await app.run_job("list_schedules")).answer
        assert {item["name"] for item in schedules} == {"daily", "heartbeat"}
        daily = next(item for item in schedules if item["name"] == "daily")
        assert daily["last_trigger"]["state"] == "succeeded"
        assert daily["last_trigger"]["trigger_id"] == queued.source.schedule.trigger_id
        assert daily["next_run_at"]
        daily["arguments"]["x"] = 99
        daily["last_trigger"]["state"] = "failed"
        assert scheduler.arguments["x"] == 1
        assert scheduler.last_trigger["state"] == "succeeded"


class Composite(BaseCompositeTask):
    def build_task_steps(self):
        yield lambda: self.run_task("demo", x=1, y=2)


def test_children_inherit_schedule_provenance(tmp_path):
    task = Composite({}, workspace_path=tmp_path, reg_name="composite", source=source())
    status = TaskRunner().run(task)
    child = status.children[0]
    metadata = read_task_metadata(task_path(tmp_path, child.task_id), child.task_id)
    assert metadata.source == status.source
    assert metadata.source.schedule.name == "daily"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["git", "pip", "restart"])
@pytest.mark.parametrize("force", [False, True])
async def test_scheduled_runs_block_all_maintenance_even_with_force(tmp_path, monkeypatch, mode, force):
    app = application(tmp_path)
    manager = app.context.components["task_manager"]["default"]
    updater = app.context.components["updater"]["default"]
    scheduled = TaskMetadata(
        version=1, task_id="base#demo#scheduled", run_id="scheduled", task_type=TaskType.BASE, source=source()
    )
    manual = scheduled.model_copy(
        update={"task_id": "base#demo#manual", "run_id": "manual", "source": TaskSource(kind="submit")}
    )
    foreign = scheduled.model_copy(update={"task_id": "base#demo#foreign", "run_id": "foreign"})
    monkeypatch.setattr(
        manager,
        "list_summaries",
        AsyncMock(return_value=[summarize_status(item) for item in [manual, foreign, scheduled]]),
    )
    monkeypatch.setattr(manager, "list_managed_run_ids", AsyncMock(return_value=["manual", "scheduled"]))
    cancel = AsyncMock()
    monkeypatch.setattr(manager, "cancel", cancel)
    monkeypatch.setattr(updater, "_plan", lambda *_: {})
    callbacks = []
    token = RESPONSE_CALLBACKS.set(callbacks)
    try:
        assert await updater.restart_blockers() == [
            {"task_id": scheduled.task_id, "run_id": "scheduled", "schedule": "daily"}
        ]
        with pytest.raises(RuntimeError, match="Active scheduled Tasks"):
            await updater.request(mode, force)
        cancel.assert_not_awaited()
        assert not callbacks
        assert updater.pending is None
        assert not app.context.metadata.get("maintenance")
    finally:
        RESPONSE_CALLBACKS.reset(token)


@pytest.mark.asyncio
async def test_terminal_and_foreign_scheduled_runs_do_not_block(tmp_path, monkeypatch):
    manager = object.__new__(LocalTaskManager)
    manager._supervisor = SimpleNamespace(run_pids={"terminal": 123})
    terminal = TaskMetadata(
        version=1,
        task_id="base#demo#terminal",
        run_id="terminal",
        task_type=TaskType.BASE,
        source=source(),
        state=TaskState.SUCCEEDED,
    )
    foreign = terminal.model_copy(update={"run_id": "foreign", "state": TaskState.RUNNING})
    monkeypatch.setattr(
        manager, "list_summaries", AsyncMock(return_value=[summarize_status(item) for item in [terminal, foreign]])
    )
    assert await manager.list_restart_blockers() == []


def test_schedule_description_uses_configured_text_or_job_description(tmp_path):
    app = application(tmp_path)
    daily = app.context.schedulers["daily"]
    assert daily.describe()["description"] == app.context.jobs["submit"].description
    daily.description = "Daily research run"
    assert daily.describe()["description"] == "Daily research run"


@pytest.mark.parametrize(
    "now, expected",
    [
        ("2026-03-08T01:30:00", 3600),
        ("2026-11-01T00:30:00", 10800),
    ],
)
def test_next_trigger_delay_uses_elapsed_time_across_dst(tmp_path, monkeypatch, now, expected):
    from zoneinfo import ZoneInfo
    import axonx.components.scheduler.cron as cron_module

    current = datetime.fromisoformat(now).replace(tzinfo=ZoneInfo("America/New_York"))

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return current.astimezone(tz)

    scheduler = application(tmp_path).context.schedulers["daily"]
    scheduler.timezone = current.tzinfo
    scheduler.cron = "30 3 * * *" if expected == 3600 else "30 2 * * *"
    monkeypatch.setattr(cron_module, "datetime", Clock)
    assert scheduler._next_delay() == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["exception", "response", "cancelled"])
async def test_failed_trigger_settles_status_and_restores_source(tmp_path, monkeypatch, failure):
    app = application(tmp_path)
    scheduler = app.context.schedulers["daily"]
    response = SimpleNamespace(success=False, answer="Rejected")
    error = RuntimeError("Rejected") if failure == "exception" else asyncio.CancelledError()
    dispatch = AsyncMock(return_value=response, side_effect=None if failure == "response" else error)
    monkeypatch.setattr(app.context.dispatcher, "run", dispatch)
    previous = TASK_SOURCE.get()
    if failure == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await scheduler._execute()
    else:
        await scheduler._execute()
    assert scheduler.last_trigger["state"] == ("cancelled" if failure == "cancelled" else "failed")
    assert scheduler.last_trigger["error"] == ("" if failure == "cancelled" else "Rejected")
    assert TASK_SOURCE.get() == previous
