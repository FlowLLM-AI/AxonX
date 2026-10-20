"""Operations navigation and durable schedule outcomes, including Job-only triggers."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from axonx.components.scheduler.history import (
    history_path,
    load_history,
    save_history,
    trigger_result,
)
from axonx.config import ApplicationConfig, resolve_app_config
from axonx.core import Application
from axonx.enums import TaskCategory
from axonx.task.builtins.demo import DemoTask
from axonx.task.catalog.resolver import _task_definition
from axonx.task.query.summary import summarize_status
from axonx.task.runtime.runner import TaskRunner
from axonx.task.storage.workspace import read_task_metadata


def application(tmp_path, history_retention_days=7):
    config = resolve_app_config(log_config=False)
    config.update(
        workspace_dir=str(tmp_path),
        log_to_console=False,
        log_to_file=False,
        enable_logo=False,
    )
    config["components"] = {}
    config["service"] = None
    config["jobs"] = {name: config["jobs"][name] for name in ("version", "list_schedules", "list_studio_pages")}
    config["schedules"] = {
        "sync": {
            "job": "version",
            "cron": "* * * * *",
            "history_retention_days": history_retention_days,
        }
    }
    config["studio"] = {
        "pages": {
            "sync": {
                "title": {"en": "Sync", "zh": "同步"},
                "view": "schedules",
                "schedules": ["sync"],
            }
        }
    }
    return Application(**config)


@pytest.mark.asyncio
async def test_job_result_survives_restart_and_navigation_is_service_defined(tmp_path):
    app = application(tmp_path)
    async with app:
        scheduler = app.context.schedulers["sync"]
        await scheduler._execute()
        record = scheduler.describe(include_history=True, history_limit=200)["last_trigger"]
        assert record["state"] == "succeeded"
        assert record["result"] and record["finished_at"]
        pages = await app.context.dispatcher.run("list_studio_pages", {})
        assert pages.answer[0]["id"] == "sync"
        assert pages.answer[0]["category"] is None
    async with application(tmp_path) as restarted:
        scheduler = restarted.context.schedulers["sync"]
        assert scheduler.describe(include_history=True, history_limit=200)["last_trigger"] == record
        assert scheduler.describe(include_history=True, history_limit=200)["history"] == [record]
        assert scheduler.describe(include_history=True, history_limit=200)["running"] == 0


def run_record(index, state="succeeded"):
    return {
        "name": "sync",
        "job": "version",
        "trigger_id": str(index),
        "triggered_at": datetime.now(UTC).isoformat(),
        "state": state,
        "error": "",
        "scheduler_id": "old",
    }


def test_history_recovers_interruption_and_keeps_active_runs(tmp_path):
    path = history_path(tmp_path, "../sync")
    assert path.parent == tmp_path / "schedules"
    records = [run_record(i) for i in range(55)] + [run_record(99, "running")]
    save_history(path, records)
    assert len(records) == 56
    restored = load_history(path)
    assert restored[-1]["state"] == "cancelled"
    assert restored[-1]["finished_at"]
    assert "Service stopped" in restored[-1]["error"]
    assert restored[0]["trigger_id"] == "0"
    assert trigger_result({"large": "x" * 20000})["truncated"]
    assert trigger_result(object())["truncated"]
    assert trigger_result({"value": float("nan")}) == {"value": None}


@pytest.mark.parametrize("retention_days", [7, 14])
@pytest.mark.parametrize("state", ["succeeded", "failed", "cancelled"])
def test_history_retention_uses_completion_time_and_preserves_active_runs(tmp_path, monkeypatch, retention_days, state):
    import axonx.components.scheduler.history as history_module

    now = datetime(2026, 10, 19, tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz)

    monkeypatch.setattr(history_module, "datetime", Clock)
    cutoff = now - timedelta(days=retention_days)
    old = (cutoff - timedelta(seconds=1)).isoformat()
    records = [
        {**run_record("expired", state), "finished_at": old},
        {**run_record("boundary", state), "finished_at": cutoff.isoformat()},
        {**run_record("offset", state), "finished_at": "2026-10-19T08:00:00+08:00"},
        {**run_record("long"), "triggered_at": old, "finished_at": now.isoformat()},
        {**run_record("legacy"), "triggered_at": old},
        {**run_record("naive"), "finished_at": now.replace(tzinfo=None).isoformat()},
        {**run_record("active", "running"), "triggered_at": old},
    ]
    path = history_path(tmp_path, "sync")
    save_history(path, records, retention_days)
    expected = ["boundary", "offset", "long", "naive", "active"]
    assert [row["trigger_id"] for row in records] == expected
    assert [row["trigger_id"] for row in load_history(path)] == expected


@pytest.mark.parametrize("days", [0, -1, True, 1.5, "7"])
def test_schedule_rejects_invalid_history_retention(days):
    from axonx.config.models import ScheduleConfig

    with pytest.raises(ValidationError):
        ScheduleConfig(job="version", cron="* * * * *", history_retention_days=days)


@pytest.mark.asyncio
async def test_scheduler_prunes_expired_history_on_startup_and_uses_config(tmp_path):
    app = application(tmp_path, history_retention_days=14)
    scheduler = app.context.schedulers["sync"]
    assert scheduler.history_retention_days == 14
    path = history_path(tmp_path, "sync")
    records = [
        {
            **run_record("expired"),
            "finished_at": (datetime.now(UTC) - timedelta(days=15)).isoformat(),
        },
        {
            **run_record("retained"),
            "finished_at": (datetime.now(UTC) - timedelta(days=10)).isoformat(),
        },
    ]
    save_history(path, records, 30)
    async with app:
        assert [row["trigger_id"] for row in scheduler.history] == ["retained"]
        assert scheduler.last_trigger["trigger_id"] == "retained"
        assert [row["trigger_id"] for row in load_history(path)] == ["retained"]
    scheduler.history_retention_days = 7
    async with app:
        assert scheduler.history == []
        assert scheduler.last_trigger is None


@pytest.mark.asyncio
async def test_overlapping_results_update_their_own_trigger(tmp_path, monkeypatch):
    app = application(tmp_path)
    scheduler = app.context.schedulers["sync"]
    gates = [asyncio.Event(), asyncio.Event()]
    calls = 0
    original = app.context.dispatcher.run

    async def dispatch(*args):
        nonlocal calls
        index = calls
        calls += 1
        await gates[index].wait()
        return await original(*args)

    monkeypatch.setattr(app.context.dispatcher, "run", dispatch)
    async with app:
        first = asyncio.create_task(scheduler._execute())
        await asyncio.sleep(0)
        second = asyncio.create_task(scheduler._execute())
        await asyncio.sleep(0)
        gates[1].set()
        await second
        gates[0].set()
        await first
        assert len(scheduler.history) == 2
        assert all(row["state"] == "succeeded" for row in load_history(history_path(tmp_path, "sync")))
        assert scheduler.last_trigger["trigger_id"] == scheduler.history[-1]["trigger_id"]


def test_category_is_persisted_and_exposed_without_changing_task_identity(tmp_path):
    class Download(DemoTask):
        category = TaskCategory.DATA_UPDATE

    task = Download({"x": 1, "y": 2}, workspace_path=tmp_path, reg_name="download")
    result = TaskRunner().run(task)
    assert result.state == "succeeded"
    assert read_task_metadata(task.task_dir, task.task_id).category == TaskCategory.DATA_UPDATE
    assert summarize_status(result).category == TaskCategory.DATA_UPDATE
    assert _task_definition("download", Download, None).category == TaskCategory.DATA_UPDATE
    assert task.task_id.startswith(f"{task.task_type.value}#download#")


@pytest.mark.parametrize(
    "page",
    [
        {"title": {"en": "Only English"}, "view": "schedules", "schedules": ["sync"]},
        {"title": {"en": "Task", "zh": "任务"}, "view": "tasks"},
        {
            "title": {"en": "Sync", "zh": "同步"},
            "view": "schedules",
            "schedules": ["sync"],
            "category": "comparison",
        },
    ],
)
def test_invalid_pages_fail_at_configuration_boundary(page):
    with pytest.raises(ValidationError):
        ApplicationConfig(studio={"pages": {"invalid": page}})


def test_composite_child_keeps_exact_parent_run(tmp_path, monkeypatch):
    from axonx.task import BaseCompositeTask
    from axonx.task.catalog import resolver

    class Download(DemoTask):
        category = TaskCategory.DATA_UPDATE

    class Parent(BaseCompositeTask):
        def build_task_steps(self):
            yield lambda: self.run_task("download", x=1, y=2)

    monkeypatch.setattr(resolver, "resolve_task", lambda name: Download)
    parent = Parent({}, workspace_path=tmp_path, reg_name="parent")
    result = TaskRunner().run(parent)
    assert result.state == "succeeded"
    from axonx.task.storage.workspace import task_path

    child = result.children[0]
    metadata = read_task_metadata(task_path(tmp_path, child.task_id), child.task_id)
    assert metadata.category == TaskCategory.DATA_UPDATE
    assert metadata.parent_run_id == result.run_id


def test_default_pages_are_generic_and_do_not_bind_plugin_schedule_names():
    config = ApplicationConfig.model_validate(resolve_app_config(log_config=False))
    assert list(config.studio.pages) == ["online", "comparison", "data", "sync"]
    assert all(not page.schedules for page in config.studio.pages.values())
    assert config.studio.pages["data"].category == TaskCategory.DATA_UPDATE
    assert config.studio.pages["comparison"].category == TaskCategory.COMPARISON


@pytest.mark.asyncio
async def test_schedule_discovery_omits_history_and_bounds_explicit_history(tmp_path):
    app = application(tmp_path)
    async with app:
        scheduler = app.context.schedulers["sync"]
        scheduler.history = [{**run_record(i), "result": {"large": "x" * 10000}} for i in range(250)]
        scheduler.history[0]["scheduler_id"] = None  # Legacy trigger without service identity.
        scheduler.last_trigger = scheduler.history[-1]
        default = (await app.run_job("list_schedules")).answer
        assert len(default) == 1
        assert "history" not in default[0]
        assert "result" not in default[0]["last_trigger"]
        assert default[0]["last_trigger"]["trigger_id"] == "249"
        assert len(scheduler.history) == 250
        assert "result" in scheduler.last_trigger
        recent = (await app.run_job("list_schedules", {"name": "sync", "include_history": True})).answer[0]
        assert len(recent["history"]) == 20
        assert recent["history_total"] == 250
        assert recent["history_scheduler_ids"] == ["old"]
        assert recent["history"][0]["trigger_id"] == "230"
        selected = (
            await app.run_job(
                "list_schedules",
                {
                    "name": "sync",
                    "include_history": True,
                    "history_limit": 2,
                },
            )
        ).answer[0]
        assert [record["trigger_id"] for record in selected["history"]] == [
            "248",
            "249",
        ]
        selected["history"][0]["result"].clear()
        assert scheduler.history[-2]["result"]
        assert (await app.run_job("list_schedules", {"name": "missing"})).answer == []
        for limit in (0, -1, 201):
            with pytest.raises(ValueError):
                scheduler.describe(include_history=True, history_limit=limit)
            with pytest.raises(ValueError):
                await app.run_job("list_schedules", {"history_limit": limit})
