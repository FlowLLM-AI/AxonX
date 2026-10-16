"""Operations navigation and durable schedule outcomes, including Job-only triggers."""

import asyncio
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from axonx.components.scheduler.history import history_path, load_history, save_history, trigger_result
from axonx.config import ApplicationConfig, resolve_app_config
from axonx.core import Application
from axonx.enums import TaskCategory
from axonx.task.builtins.demo import DemoTask
from axonx.task.catalog.resolver import _task_definition
from axonx.task.query.summary import summarize_status
from axonx.task.runtime.runner import TaskRunner
from axonx.task.storage.workspace import read_task_metadata


def application(tmp_path):
    config = resolve_app_config(log_config=False)
    config.update(workspace_dir=str(tmp_path), log_to_console=False, log_to_file=False, enable_logo=False)
    config["components"] = {}
    config["service"] = None
    config["jobs"] = {name: config["jobs"][name] for name in ("version", "list_schedules", "list_studio_pages")}
    config["schedules"] = {"sync": {"job": "version", "cron": "* * * * *"}}
    config["studio"] = {
        "pages": {"sync": {"title": {"en": "Sync", "zh": "同步"}, "view": "schedules", "schedules": ["sync"]}}
    }
    return Application(**config)


@pytest.mark.asyncio
async def test_job_result_survives_restart_and_navigation_is_service_defined(tmp_path):
    app = application(tmp_path)
    async with app:
        scheduler = app.context.schedulers["sync"]
        await scheduler._execute()
        record = scheduler.describe()["last_trigger"]
        assert record["state"] == "succeeded"
        assert record["result"] and record["finished_at"]
        pages = await app.context.dispatcher.run("list_studio_pages", {})
        assert pages.answer[0]["id"] == "sync"
        assert pages.answer[0]["category"] is None
    async with application(tmp_path) as restarted:
        scheduler = restarted.context.schedulers["sync"]
        assert scheduler.describe()["last_trigger"] == record
        assert scheduler.describe()["history"] == [record]
        assert scheduler.describe()["running"] == 0


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
    assert len(records) == 51
    restored = load_history(path)
    assert restored[-1]["state"] == "cancelled"
    assert restored[-1]["finished_at"]
    assert "Service stopped" in restored[-1]["error"]
    assert restored[0]["trigger_id"] == "5"
    assert trigger_result({"large": "x" * 20000})["truncated"]
    assert trigger_result(object())["truncated"]
    assert trigger_result({"value": float("nan")}) == {"value": None}


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
        {"title": {"en": "Sync", "zh": "同步"}, "view": "schedules", "schedules": ["sync"], "category": "comparison"},
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
    assert list(config.studio.pages) == ["sync", "data", "online", "comparison"]
    assert all(not page.schedules for page in config.studio.pages.values())
    assert config.studio.pages["data"].category == TaskCategory.DATA_UPDATE
    assert config.studio.pages["comparison"].category == TaskCategory.COMPARISON
