"""Focused contracts for the refactored Task runtime and manager services."""

import asyncio
import re
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from axonx.components.job import LogEvent
from axonx.components.task_manager.local.manager import LocalTaskManager
from axonx.components.task_manager.local.supervisor import WorkerExit
from axonx.core import Application
from axonx.enums import TaskState, TaskType
from axonx.task.builtins import DemoTask
from axonx.task.core import task_type_from_id
from axonx.task.query.stream import stream_task
from axonx.task.storage.events import LOG_WINDOW_BYTES, read_event_lines
from axonx.task.storage.logs import TaskLogReader
from axonx.task.storage.workspace import TaskStatus, write_status


def test_task_context_is_immutable_and_step_state_is_separate(tmp_path):
    task = DemoTask({"x": 2, "y": 3}, workspace_path=tmp_path, reg_name="demo")

    task.state["working"] = True
    assert task.state == {"working": True}
    assert task.context.workspace_path == tmp_path.resolve()
    with pytest.raises(FrozenInstanceError):
        task.context.task_id = "changed"


def test_named_task_id_is_stable(tmp_path):
    task = DemoTask(
        {"x": 1, "y": 1, "task_name": "sample"},
        workspace_path=tmp_path,
        reg_name="demo",
        created_at=datetime(2026, 9, 21, 14, 35, 27, tzinfo=UTC),
    )

    assert task.task_id == "base#demo#sample"
    assert task.is_generated_name is False


def test_unnamed_task_gets_hour_prefixed_random_name(tmp_path):
    task = DemoTask(
        {"x": 1, "y": 1},
        workspace_path=tmp_path,
        reg_name="demo",
        created_at=datetime(2026, 9, 21, 14, 35, 27, tzinfo=UTC),
    )

    assert re.fullmatch(r"2026092114[A-Za-z0-9]{4}", task.input_params.task_name)
    assert task.task_id == f"base#demo#{task.input_params.task_name}"
    assert task.is_generated_name is True


def test_old_timestamped_task_ids_are_rejected():
    with pytest.raises(ValueError, match="Invalid task ID"):
        task_type_from_id("base#demo#sample#2026092114")


def test_include_time_is_not_a_task_option(tmp_path):
    with pytest.raises(ValueError, match="include_time"):
        DemoTask(
            {"x": 1, "y": 1, "include_time": True},
            workspace_path=tmp_path,
            reg_name="demo",
        )


def test_task_status_reads_legacy_execution_id_as_run_id():
    status = TaskStatus.model_validate(
        {
            "task_id": "analysis#sample#legacy",
            "execution_id": "legacy-run",
            "task_type": "analysis",
        }
    )

    assert status.run_id == "legacy-run"
    assert status.model_dump()["run_id"] == "legacy-run"
    assert "execution_id" not in status.model_dump()


def test_log_windows_do_not_split_utf8_codepoints(tmp_path):
    path = tmp_path / "task.log"
    path.write_text("a你b", encoding="utf-8")
    reader = TaskLogReader(tmp_path)

    first = reader.read(path, offset=0, limit=2)
    second = reader.read(path, offset=first.next_offset, limit=2)
    tail = reader.read(path, offset=-1, limit=2)

    assert first.content == "a你"
    assert second.content == "b"
    assert tail.content == "你b"
    assert first.next_offset == len("a你".encode())


def test_event_reader_restarts_after_journal_replacement(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text("one\ntwo\n", encoding="utf-8")
    offset, lines = read_event_lines(path, 0)
    assert lines == ["one", "two"]

    path.write_text("new\n", encoding="utf-8")
    next_offset, lines = read_event_lines(path, offset)
    assert lines == ["new"]
    assert next_offset == len("new\n")


async def test_stream_reports_task_disappearance_instead_of_success(tmp_path):
    status = TaskStatus(
        task_id="analysis#sample#gone",
        run_id="gone",
        task_type=TaskType.ANALYSIS,
        state=TaskState.RUNNING,
    )
    calls = 0

    async def read_status(_task_id):
        nonlocal calls
        calls += 1
        if calls == 1:
            return status
        raise KeyError(status.task_id)

    class Logger:
        def warning(self, _message):
            pass

    with pytest.raises(KeyError):
        await anext(
            stream_task(
                tmp_path,
                TaskLogReader(tmp_path),
                read_status,
                Logger(),
                status.task_id,
                0.01,
            )
        )


async def test_terminal_stream_drains_all_log_windows(tmp_path):
    log_path = tmp_path / "task.log"
    content = "x" * (LOG_WINDOW_BYTES * 2 + 17)
    log_path.write_text(content, encoding="utf-8")
    status = TaskStatus(
        task_id="analysis#sample#done",
        run_id="done",
        task_type=TaskType.ANALYSIS,
        state=TaskState.SUCCEEDED,
        log_path=str(log_path),
    )

    async def read_status(_task_id):
        return status

    class Logger:
        def warning(self, _message):
            pass

    events = [
        event
        async for event in stream_task(
            tmp_path,
            TaskLogReader(tmp_path),
            read_status,
            Logger(),
            status.task_id,
            0.01,
        )
    ]
    assert all(isinstance(event, LogEvent) for event in events)
    assert "".join(event.content for event in events) == content
    assert len(events) == 3


async def test_stream_follows_log_path_created_after_subscription(tmp_path):
    log_path = tmp_path / "task.log"
    log_path.write_text("live log\n", encoding="utf-8")
    queued = TaskStatus(
        task_id="analysis#sample#late-log",
        run_id="late-log",
        task_type=TaskType.ANALYSIS,
        state=TaskState.QUEUED,
    )
    finished = queued.model_copy(
        update={"state": TaskState.SUCCEEDED, "log_path": str(log_path)}
    )
    calls = 0

    async def read_status(_task_id):
        nonlocal calls
        calls += 1
        return queued if calls == 1 else finished

    class Logger:
        def warning(self, _message):
            pass

    events = [
        event
        async for event in stream_task(
            tmp_path,
            TaskLogReader(tmp_path),
            read_status,
            Logger(),
            queued.task_id,
            0.001,
        )
    ]

    assert "".join(event.content for event in events if isinstance(event, LogEvent)) == (
        "live log\n"
    )


async def test_statuses_are_sorted_by_creation_time_not_task_id():
    now = datetime.now(UTC)
    older = TaskStatus(
        task_id="analysis#z#older",
        run_id="older",
        task_type=TaskType.ANALYSIS,
        created_at=now - timedelta(days=1),
    )
    newer = TaskStatus(
        task_id="analysis#a#newer",
        run_id="newer",
        task_type=TaskType.ANALYSIS,
        created_at=now,
    )

    class Index:
        async def statuses(self):
            return {older.task_id: older, newer.task_id: newer}

    manager = object.__new__(LocalTaskManager)
    manager.repository = Index()
    assert [item.task_id for item in await manager.list_statuses()] == [
        newer.task_id,
        older.task_id,
    ]


async def test_cancel_targets_the_managed_run_instead_of_the_persisted_pid():
    status = TaskStatus(
        task_id="analysis#sample#running",
        run_id="current-run",
        task_type=TaskType.ANALYSIS,
        state=TaskState.RUNNING,
        pid=41,
    )
    cancelled = []
    finished = []

    class Repository:
        async def entry(self, _task_id):
            return type("Entry", (), {"status": status})()

    class Supervisor:
        async def cancel_run(self, run_id):
            cancelled.append(run_id)
            return True

    async def finish(*args):
        finished.append(args)

    manager = object.__new__(LocalTaskManager)
    manager._lock = asyncio.Lock()
    manager.repository = Repository()
    manager._supervisor = Supervisor()
    manager._finish = finish

    assert await manager.cancel(status.task_id) is True
    assert cancelled == [status.run_id]
    assert finished[0][0] is status


async def test_worker_exit_targets_its_task_and_run_directly():
    status = TaskStatus(
        task_id="analysis#sample#running",
        run_id="current-run",
        task_type=TaskType.ANALYSIS,
        state=TaskState.RUNNING,
    )
    settled = []

    class Repository:
        async def entry(self, task_id):
            assert task_id == status.task_id
            return type("Entry", (), {"status": status})()

    async def settle(*args, **kwargs):
        settled.append((args, kwargs))

    manager = object.__new__(LocalTaskManager)
    manager.repository = Repository()
    manager._settle_dead_task = settle

    await manager._handle_worker_exit(
        WorkerExit(7, "boom", status.task_id, status.run_id)
    )

    assert settled == [
        (
            (status.task_id, 7, "Worker exited without final status (code 7): boom"),
            {"gone": True},
        )
    ]


async def test_reaper_recovers_after_one_failed_round(monkeypatch):
    repairs = 0
    logged = 0

    class Logger:
        def exception(self, _message):
            nonlocal logged
            logged += 1

    class Manager:
        _reaper_interval = 1
        logger = Logger()

        async def _repair_dead_tasks(self):
            nonlocal repairs
            repairs += 1
            if repairs == 1:
                raise OSError("transient")
            raise asyncio.CancelledError

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    with pytest.raises(asyncio.CancelledError):
        await LocalTaskManager._reap_periodically(Manager())
    assert repairs == 2
    assert logged == 1


async def test_submission_returns_queryable_task_handle(tmp_path):
    app = Application(
        workspace_dir=str(tmp_path),
        log_dir=str(tmp_path / "logs"),
        enable_logo=False,
        log_to_console=False,
        log_to_file=False,
        components={
            "task_repository": {
                "default": {
                    "backend": "local",
                    "force_polling": True,
                    "debounce": 20,
                    "step": 20,
                    "poll_delay_ms": 20,
                }
            },
            "task_manager": {
                "default": {
                    "backend": "local",
                    "task_repository": "default",
                    "reaper_interval_seconds": 0.1,
                }
            },
        },
        jobs={"submit": {"steps": [{"backend": "submit_task"}]}},
    )

    async with app:
        response = await app.run_job("submit", {"task": "demo", "x": 2, "y": 3})
        handle = response.answer
        manager = app.context.components["task_manager"]["default"]
        for _ in range(50):
            status = await manager.get_status(handle.task_id)
            if status.state.is_terminal:
                break
            await asyncio.sleep(0.1)

    assert response.success is True
    assert status.run_id == handle.run_id
    assert status.state == TaskState.SUCCEEDED
    assert status.result["result"] == 5


async def test_named_submission_replaces_completed_task(tmp_path):
    app = Application(
        workspace_dir=str(tmp_path),
        log_dir=str(tmp_path / "logs"),
        enable_logo=False,
        log_to_console=False,
        log_to_file=False,
        components={
            "task_repository": {"default": {"backend": "local"}},
            "task_manager": {"default": {"backend": "local"}},
        },
        jobs={"submit": {"steps": [{"backend": "submit_task"}]}},
    )

    async with app:
        manager = app.context.components["task_manager"]["default"]
        first = (
            await app.run_job(
                "submit", {"task": "demo", "task_name": "latest", "x": 2, "y": 3}
            )
        ).answer
        for _ in range(50):
            if (await manager.get_status(first.task_id)).state.is_terminal:
                break
            await asyncio.sleep(0.1)

        second = (
            await app.run_job(
                "submit", {"task": "demo", "task_name": "latest", "x": 4, "y": 5}
            )
        ).answer
        for _ in range(50):
            status = await manager.get_status(second.task_id)
            if status.state.is_terminal:
                break
            await asyncio.sleep(0.1)

    assert first.task_id == second.task_id == "base#demo#latest"
    assert first.run_id != second.run_id
    assert status.state == TaskState.SUCCEEDED
    assert status.result["result"] == 9


async def test_named_submission_cannot_replace_active_task(tmp_path):
    task = DemoTask(
        {"x": 1, "y": 1, "task_name": "active"},
        workspace_path=tmp_path,
        reg_name="demo",
    )
    task.task_dir.mkdir(parents=True)
    write_status(
        task.task_dir,
        TaskStatus(
            task_id=task.task_id,
            run_id="active-run",
            task_type=task.task_type,
            state=TaskState.RUNNING,
        ),
    )
    class Manager:
        workspace_path = tmp_path

    with pytest.raises(FileExistsError, match="Active Task"):
        await LocalTaskManager._reserve(Manager(), task, replace=True)
