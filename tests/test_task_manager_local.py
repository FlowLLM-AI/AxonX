"""Workspace-backed task manager behavior."""

import asyncio
import json
import os

import pytest

from axonx import Application
from axonx.components.task_manager.local.index import TaskIndex
from axonx.components.task_manager.local.process import WorkerExit
from axonx.config import resolve_app_config
from axonx.enums import TaskState, TaskType
from axonx.schema import TaskLogChunk, TaskStatus
from axonx.utils.fs import atomic_write_json

LOCAL_COMPONENTS = {"task_manager": {"default": {"backend": "local", "force_polling": True, "poll_delay_ms": 50, "step": 50, "debounce": 1000}}}


def test_task_index_watches_only_task_json_files(tmp_path):
    index = TaskIndex(tmp_path, None)
    assert index.watch.force_polling is True
    assert index.watch.step == index.watch.poll_delay_ms == 3_000
    task = tmp_path / "analysis" / "analysis#sample#one"
    assert index._watch_file(None, str(task / "status.json"))
    assert index._watch_file(None, str(task / "metadata.json"))
    assert not index._watch_file(None, str(task / "artifact.txt"))
    assert not index._watch_file(None, str(task))
    assert not index._watch_file(None, str(tmp_path / "etl" / task.name / "status.json"))


async def _wait_for(predicate):
    for _ in range(140):
        if await predicate():
            return
        await asyncio.sleep(0.05)
    assert await predicate()


async def test_task_index_watches_status_metadata_and_directory_removal(tmp_path):
    task_id = "analysis#sample#live"
    directory = tmp_path / "analysis" / task_id
    app = Application(workspace_dir=str(tmp_path), components=LOCAL_COMPONENTS)
    async with app:
        manager = app.get_component("task_manager")
        directory.mkdir(parents=True)
        status = TaskStatus(task_id=task_id, task_type=TaskType.ANALYSIS, state=TaskState.RUNNING, pid=os.getpid())
        atomic_write_json(directory / "status.json", status.model_dump(mode="json"))

        async def has_running():
            return task_id in await manager.list_ids() and (await manager.get_status(task_id)).state == TaskState.RUNNING

        await _wait_for(has_running)
        with pytest.raises(KeyError):
            await manager.get_graph(task_id)
        atomic_write_json(directory / "metadata.json", {
            "task_id": task_id,
            "task_type": "analysis",
            "reg_name": "sample",
            "created_at": "2026-09-18T00:00:00Z",
            "input_params": {"source_tasks": []},
        })

        async def has_metadata():
            try:
                return not (await manager.get_graph(task_id)).nodes[0].missing
            except KeyError:
                return False

        await _wait_for(has_metadata)
        await asyncio.sleep(1)
        status.state = TaskState.SUCCEEDED
        atomic_write_json(directory / "status.json", status.model_dump(mode="json"))

        async def has_succeeded():
            return (await manager.get_status(task_id)).state == TaskState.SUCCEEDED

        await _wait_for(has_succeeded)
        assert await manager.delete([task_id]) == [task_id]
        assert not directory.exists()
        assert await manager.list_ids() == []


async def test_metadata_only_task_is_visible_and_deletable(tmp_path):
    task_id = "etl#sample#old"
    directory = tmp_path / "etl" / task_id
    directory.mkdir(parents=True)
    atomic_write_json(directory / "metadata.json", {
        "task_id": task_id,
        "task_type": "etl",
        "reg_name": "sample",
        "created_at": "2026-09-18T00:00:00Z",
        "input_params": {"source_tasks": []},
    })
    async with Application(workspace_dir=str(tmp_path), components=LOCAL_COMPONENTS) as app:
        manager = app.get_component("task_manager")
        assert await manager.list_ids() == []
        assert await manager.list_statuses() == []
        with pytest.raises(KeyError):
            await manager.get_status(task_id)
        assert (await manager.get_graph(task_id)).nodes[0].task_name == "sample"
        assert await manager.delete([task_id]) == [task_id]
    assert not directory.exists()


async def test_missing_task_queries_use_key_error(tmp_path):
    async with Application(workspace_dir=str(tmp_path), components=LOCAL_COMPONENTS) as app:
        manager = app.get_component("task_manager")
        for query in (manager.get_status, manager.get_graph, manager.read_log):
            with pytest.raises(KeyError, match="etl#sample#missing"):
                await query("etl#sample#missing")


async def test_delete_removes_status_artifacts_and_dedicated_log(tmp_path):
    task_id = "analysis#sample#done"
    directory = tmp_path / "analysis" / task_id
    directory.mkdir(parents=True)
    (directory / "artifact.txt").write_text("result")
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_path = log_dir / "task.log"
    log_path.write_text("finished")
    status = TaskStatus(task_id=task_id, task_type=TaskType.ANALYSIS, state=TaskState.SUCCEEDED, log_path=str(log_path))
    atomic_write_json(directory / "status.json", status.model_dump(mode="json"))
    async with Application(workspace_dir=str(tmp_path), log_dir=str(log_dir), components=LOCAL_COMPONENTS) as app:
        manager = app.get_component("task_manager")
        assert await manager.delete([task_id, task_id, "bad-id"]) == [task_id]
    assert not directory.exists()
    assert not log_path.exists()


async def test_worker_exit_writes_final_status_file(tmp_path):
    task_id = "analysis#sample#crashed"
    directory = tmp_path / "analysis" / task_id
    directory.mkdir(parents=True)
    status = TaskStatus(task_id=task_id, task_type=TaskType.ANALYSIS, state=TaskState.RUNNING, pid=os.getpid())
    atomic_write_json(directory / "status.json", status.model_dump(mode="json"))
    async with Application(workspace_dir=str(tmp_path), components=LOCAL_COMPONENTS) as app:
        manager = app.get_component("task_manager")
        await manager._handle_worker_exit(WorkerExit(os.getpid(), 2, "boom"))
        stored = json.loads((directory / "status.json").read_text())
        assert stored["state"] == "failed"
        assert stored["exit_code"] == 2
        assert "boom" in stored["error"]


async def test_submitted_task_is_indexed_without_http_reporting(tmp_path):
    async with Application(workspace_dir=str(tmp_path), components=LOCAL_COMPONENTS) as app:
        manager = app.get_component("task_manager")
        await manager.submit(["--task", "demo", "--x", "1", "--y", "2", "--task-name", "disk-run", "--include-time", "false"])
        task_id = "base#demo#disk-run"

        async def completed():
            if task_id not in await manager.list_ids():
                return False
            return (await manager.get_status(task_id)).state == TaskState.SUCCEEDED

        await _wait_for(completed)
        await asyncio.gather(*tuple(manager._supervisor.monitors))
        stored = json.loads((tmp_path / "base" / task_id / "status.json").read_text())
        assert stored["result"]["result"] == 3
        assert task_id in await manager.list_ids()


async def test_running_task_cannot_be_deleted_and_cancel_writes_file(tmp_path, monkeypatch):
    task_id = "analysis#sample#running"
    directory = tmp_path / "analysis" / task_id
    directory.mkdir(parents=True)
    status = TaskStatus(task_id=task_id, task_type=TaskType.ANALYSIS, state=TaskState.RUNNING, pid=os.getpid())
    atomic_write_json(directory / "status.json", status.model_dump(mode="json"))
    async with Application(workspace_dir=str(tmp_path), components=LOCAL_COMPONENTS) as app:
        manager = app.get_component("task_manager")
        assert await manager.delete([task_id]) == []

        async def cancelled(pid):
            assert pid == os.getpid()
            return True

        monkeypatch.setattr(manager._supervisor, "cancel", cancelled)
        assert await manager.cancel(task_id)
        assert json.loads((directory / "status.json").read_text())["state"] == "cancelled"


async def test_restart_marks_dead_worker_failed_on_disk(tmp_path):
    task_id = "analysis#sample#interrupted"
    directory = tmp_path / "analysis" / task_id
    directory.mkdir(parents=True)
    status = TaskStatus(task_id=task_id, task_type=TaskType.ANALYSIS, state=TaskState.RUNNING, pid=999999999)
    atomic_write_json(directory / "status.json", status.model_dump(mode="json"))
    async with Application(workspace_dir=str(tmp_path), components=LOCAL_COMPONENTS) as app:
        assert (await app.get_component("task_manager").get_status(task_id)).state == TaskState.FAILED
    assert json.loads((directory / "status.json").read_text())["state"] == "failed"


async def test_dead_unmanaged_task_is_repaired_while_manager_runs(tmp_path):
    task_id = "analysis#sample#lost"
    directory = tmp_path / "analysis" / task_id
    async with Application(workspace_dir=str(tmp_path), components=LOCAL_COMPONENTS) as app:
        manager = app.get_component("task_manager")
        directory.mkdir(parents=True)
        status = TaskStatus(task_id=task_id, task_type=TaskType.ANALYSIS, state=TaskState.RUNNING, pid=999999999)
        atomic_write_json(directory / "status.json", status.model_dump(mode="json"))

        async def has_failed():
            return task_id in await manager.list_ids() and (await manager.get_status(task_id)).state == TaskState.FAILED

        await _wait_for(has_failed)
        assert json.loads((directory / "status.json").read_text())["state"] == "failed"


async def test_log_reader_bounds_and_rejects_outside_paths(tmp_path):
    task_id = "analysis#sample#logged"
    directory = tmp_path / "analysis" / task_id
    directory.mkdir(parents=True)
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_path = log_dir / "worker.log"
    log_path.write_text("a" * 1200 + "ghij")
    status = TaskStatus(task_id=task_id, task_type=TaskType.ANALYSIS, state=TaskState.SUCCEEDED, log_path=str(log_path))
    atomic_write_json(directory / "status.json", status.model_dump(mode="json"))
    config = resolve_app_config(workspace_dir=str(tmp_path), log_dir=str(log_dir))
    config["components"]["task_manager"]["default"].update(LOCAL_COMPONENTS["task_manager"]["default"])
    async with Application(**config) as app:
        assert isinstance(await app.get_component("task_manager").read_log(task_id), TaskLogChunk)
        response = await app.run_job("read_task_log", task_id=task_id, offset=-1, limit=1024)
        assert response.answer["content"] == "a" * 1020 + "ghij"
        await asyncio.sleep(1)
        status.log_path = str(tmp_path / "outside.log")
        atomic_write_json(directory / "status.json", status.model_dump(mode="json"))
        async def log_path_updated():
            return (await app.get_component("task_manager").get_status(task_id)).log_path == status.log_path

        await _wait_for(log_path_updated)
        response = await app.run_job("read_task_log", task_id=task_id)
        assert response.success is False
        assert "outside the configured log directory" in response.answer
