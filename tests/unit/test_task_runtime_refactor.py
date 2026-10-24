"""Focused contracts for the refactored Task runtime and manager services."""

import re
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from axonx.components.job import LogEvent
from axonx.components.job.events import ProgressEvent
from axonx.enums import TaskState, TaskType
from axonx.task.builtins import DemoTask
from axonx.task.core import task_type_from_id
from axonx.task.query.stream import stream_task
from axonx.task.runtime.runner import TaskRunner
from axonx.task.storage.events import LOG_WINDOW_BYTES, append_event, read_event_lines
from axonx.task.storage.logs import TaskLogReader
from axonx.task.storage.workspace import (
    EVENTS_FILE,
    TaskMetadata,
    read_task_metadata,
    task_path,
    write_task_metadata,
)
from axonx.utils.logging import LoggingConfig, configure_logging


def test_success_is_published_with_matching_persisted_output(tmp_path):
    task = DemoTask(
        {"x": 2, "y": 3, "task_name": "finished"},
        workspace_path=tmp_path,
        reg_name="demo",
    )
    observed = []

    def on_status(status):
        if status.state == TaskState.SUCCEEDED:
            persisted = read_task_metadata(task.task_dir, task.task_id)
            assert persisted == status
            assert persisted.output_params["result"] == 5
            observed.append(persisted.state)

    result = TaskRunner(emit=on_status).run(task)

    assert result.state == TaskState.SUCCEEDED
    assert observed == [TaskState.SUCCEEDED]


@pytest.mark.parametrize("failure", ["active", "unknown", "symlink", "mkdir"])
def test_runner_closes_rejected_task_once_without_overwriting_directory(tmp_path, monkeypatch, failure):
    task = DemoTask(
        {"x": 1, "y": 2, "task_name": "rejected"},
        workspace_path=tmp_path,
        reg_name="demo",
    )
    if failure == "active":
        task.task_dir.mkdir(parents=True)
        write_task_metadata(
            task.task_dir,
            TaskMetadata(
                version=1,
                task_id=task.task_id,
                run_id="foreign",
                task_type=TaskType.BASE,
                state=TaskState.RUNNING,
            ),
        )
    elif failure == "unknown":
        task.task_dir.mkdir(parents=True)
        (task.task_dir / "foreign.txt").write_text("retain")
    elif failure == "symlink":
        task.task_dir.parent.mkdir(parents=True)
        foreign = tmp_path / "foreign"
        foreign.mkdir()
        (foreign / "foreign.txt").write_text("retain")
        task.task_dir.symlink_to(foreign, target_is_directory=True)
    else:
        monkeypatch.setattr(TaskRunner, "_prepare_directory", Mock(side_effect=OSError("mkdir failed")))
    before = {path.name: path.read_bytes() for path in task.task_dir.glob("*")} if task.task_dir.exists() else {}
    task.close = Mock()
    runner = TaskRunner()
    with pytest.raises((FileExistsError, ValueError, OSError)):
        runner.run(task)
    task.close.assert_called_once_with()
    after = {path.name: path.read_bytes() for path in task.task_dir.glob("*")} if task.task_dir.exists() else {}
    assert after == before
    assert task._progress is None
    assert runner.task is runner.status is runner.step is None


@pytest.mark.parametrize("with_other_source", [False, True])
def test_task_rejects_self_source_before_replacing_outputs(tmp_path, with_other_source):
    first = DemoTask(
        {"x": 1, "y": 2, "task_name": "shared"},
        workspace_path=tmp_path,
        reg_name="demo",
    )
    TaskRunner().run(first)
    (first.task_dir / "value.txt").write_text("preserve")
    before = {path.name: path.read_bytes() for path in first.task_dir.glob("*")}
    sources = first.task_id + (",etl#upstream#other" if with_other_source else "")
    with pytest.raises(ValueError, match="own Task ID"):
        DemoTask(
            {"x": 3, "y": 4, "task_name": "shared", "source_tasks": sources},
            workspace_path=tmp_path,
            reg_name="demo",
        )
    assert {path.name: path.read_bytes() for path in first.task_dir.glob("*")} == before


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


def test_task_status_requires_run_id():
    with pytest.raises(ValueError):
        TaskMetadata.model_validate(
            {
                "task_id": "analysis#sample#run",
                "execution_id": "old",
                "task_type": "analysis",
            }
        )


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
    status = TaskMetadata(
        version=1,
        task_id="analysis#sample#gone",
        run_id="gone",
        task_type=TaskType.ANALYSIS,
        state=TaskState.RUNNING,
    )
    calls = 0

    async def read_task_metadata(_task_id):
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
                read_task_metadata,
                Logger(),
                status.task_id,
                0.01,
            )
        )


async def test_terminal_stream_drains_all_log_windows(tmp_path):
    log_path = tmp_path / "task.log"
    content = "x" * (LOG_WINDOW_BYTES * 2 + 17)
    log_path.write_text(content, encoding="utf-8")
    status = TaskMetadata(
        version=1,
        task_id="analysis#sample#done",
        run_id="done",
        task_type=TaskType.ANALYSIS,
        state=TaskState.SUCCEEDED,
        log_path=str(log_path),
    )

    async def read_task_metadata(_task_id):
        return status

    class Logger:
        def warning(self, _message):
            pass

    events = [
        event
        async for event in stream_task(
            tmp_path,
            TaskLogReader(tmp_path),
            read_task_metadata,
            Logger(),
            status.task_id,
            0.01,
        )
    ]
    assert all(isinstance(event, LogEvent) for event in events)
    assert "".join(event.content for event in events) == content
    assert len(events) == 3


async def test_terminal_stream_finishes_while_shared_log_keeps_growing(tmp_path):
    path = tmp_path / "shared.log"
    content = "feature completed\n" + "x" * LOG_WINDOW_BYTES
    path.write_text(content)
    status = TaskMetadata(
        version=1,
        task_id="analysis#sample#done",
        run_id="done",
        task_type=TaskType.ANALYSIS,
        state=TaskState.SUCCEEDED,
        log_path=str(path),
    )
    calls = 0

    async def read_status(_task_id):
        nonlocal calls
        calls += 1
        if calls > 8:
            raise AssertionError("Terminal stream waited for the sibling log to stop")
        if calls > 1:
            with path.open("a") as handle:
                handle.write("train is still running\n")
        return status

    events = [
        event
        async for event in stream_task(tmp_path, TaskLogReader(tmp_path), read_status, Mock(), status.task_id, 0.001)
    ]
    assert "".join(event.content for event in events) == content


@pytest.mark.parametrize("state", [TaskState.SUCCEEDED, TaskState.FAILED])
@pytest.mark.parametrize("with_log", [True, False])
async def test_stream_drains_events_written_during_terminal_transition(tmp_path, state, with_log):
    path = tmp_path / "task.log"
    path.write_text("running\n", encoding="utf-8")
    running = TaskMetadata(
        version=1,
        task_id="analysis#sample#transition",
        run_id="transition",
        task_type=TaskType.ANALYSIS,
        state=TaskState.RUNNING,
        log_path=str(path) if with_log else "",
    )
    journal = task_path(tmp_path, running.task_id) / EVENTS_FILE
    journal.parent.mkdir(parents=True)
    append_event(journal, ProgressEvent(name="finish", percentage=0))
    calls = 0

    async def read_status(_task_id):
        nonlocal calls
        calls += 1
        if calls == 1:
            return running
        if calls == 2:
            with path.open("a", encoding="utf-8") as handle:
                handle.write("final log\n")
            append_event(journal, ProgressEvent(name="finish", percentage=100))
        return running.model_copy(update={"state": state})

    events = [
        event
        async for event in stream_task(tmp_path, TaskLogReader(tmp_path), read_status, Mock(), running.task_id, 0.001)
    ]
    assert [event.percentage for event in events if isinstance(event, ProgressEvent)] == [0, 100]
    assert "".join(event.content for event in events if isinstance(event, LogEvent)) == (
        "running\nfinal log\n" if with_log else ""
    )


@pytest.mark.parametrize("fails", [False, True])
def test_terminal_status_is_published_after_final_log(tmp_path, fails):
    class LoggedTask(DemoTask):
        def finish(self):
            if fails:
                raise RuntimeError("failure marker")
            super().finish()

    configure_logging(LoggingConfig(log_dir=tmp_path / "logs", log_to_console=False))
    try:
        task = LoggedTask({"x": 1, "y": 2}, workspace_path=tmp_path / "workspace", reg_name="demo")
        observed = []

        def on_status(status):
            if status.state.is_terminal:
                content = Path(status.log_path).read_text(encoding="utf-8")
                assert ("Task failed" if fails else "Task completed") in content
                if fails:
                    assert "RuntimeError: failure marker" in content
                observed.append(status.state)

        runner = TaskRunner(emit=on_status)
        if fails:
            with pytest.raises(RuntimeError, match="failure marker"):
                runner.run(task)
        else:
            runner.run(task)
        assert observed == [TaskState.FAILED if fails else TaskState.SUCCEEDED]
    finally:
        configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))


async def test_terminal_stream_replays_journal_when_log_has_expired(tmp_path):
    status = TaskMetadata(
        version=1,
        task_id="analysis#sample#expired",
        run_id="expired",
        task_type=TaskType.ANALYSIS,
        state=TaskState.SUCCEEDED,
        log_path=str(tmp_path / "expired.log"),
    )
    journal = task_path(tmp_path, status.task_id) / EVENTS_FILE
    journal.parent.mkdir(parents=True)
    append_event(journal, ProgressEvent(name="finish", percentage=100))

    async def read_status(_task_id):
        return status

    events = [
        event
        async for event in stream_task(tmp_path, TaskLogReader(tmp_path), read_status, Mock(), status.task_id, 0.001)
    ]
    assert events == [ProgressEvent(name="finish", percentage=100)]
    with pytest.raises(FileNotFoundError, match="retained for 7 days"):
        TaskLogReader(tmp_path).read(Path(status.log_path))


@pytest.mark.parametrize("final_content", ["final\n", ""])
async def test_terminal_stream_handles_log_truncation(tmp_path, final_content):
    path = tmp_path / "task.log"
    path.write_text("previous content\n", encoding="utf-8")
    running = TaskMetadata(
        version=1,
        task_id="analysis#sample#truncated",
        run_id="truncated",
        task_type=TaskType.ANALYSIS,
        state=TaskState.RUNNING,
        log_path=str(path),
    )
    calls = 0

    async def read_status(_task_id):
        nonlocal calls
        calls += 1
        if calls == 1:
            return running
        path.write_text(final_content, encoding="utf-8")
        return running.model_copy(update={"state": TaskState.SUCCEEDED})

    events = [
        event
        async for event in stream_task(tmp_path, TaskLogReader(tmp_path), read_status, Mock(), running.task_id, 0.001)
    ]
    assert [event.content for event in events] == ["previous content\n", final_content]
    assert events[-1].reset


async def test_stream_follows_log_path_created_after_subscription(tmp_path):
    log_path = tmp_path / "task.log"
    log_path.write_text("live log\n", encoding="utf-8")
    queued = TaskMetadata(
        version=1,
        task_id="analysis#sample#late-log",
        run_id="late-log",
        task_type=TaskType.ANALYSIS,
        state=TaskState.QUEUED,
    )
    finished = queued.model_copy(update={"state": TaskState.SUCCEEDED, "log_path": str(log_path)})
    calls = 0

    async def read_task_metadata(_task_id):
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
            read_task_metadata,
            Logger(),
            queued.task_id,
            0.001,
        )
    ]

    assert "".join(event.content for event in events if isinstance(event, LogEvent)) == ("live log\n")


@pytest.mark.parametrize("link", ["kind", "task", "status"])
def test_strict_status_read_refuses_symlinks(tmp_path, link):
    status = TaskMetadata(
        version=1,
        task_id="base#demo#linked",
        run_id="run",
        task_type=TaskType.BASE,
        state=TaskState.RUNNING,
    )
    directory = task_path(tmp_path, status.task_id)
    directory.mkdir(parents=True)
    write_task_metadata(directory, status)
    path = {
        "kind": directory.parent,
        "task": directory,
        "status": directory / "metadata.json",
    }[link]
    target = tmp_path / "saved"
    path.rename(target)
    path.symlink_to(target, target_is_directory=link != "status")

    assert read_task_metadata(directory, status.task_id, strict_io=True) is None
