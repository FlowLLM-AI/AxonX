"""Every Task type preserves execution metadata across replacements and failures."""

import fcntl
import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest

from axonx.task.builtins.demo import DemoTask
from axonx.task.models.identity import TaskState, TaskType
from axonx.task.runtime import lifecycle
from axonx.task.runtime.executor import TaskExecutor
from axonx.task.runtime.progress import TaskProgress
from axonx.task.storage.logs import TaskJournal
from axonx.task.storage.workspace import write_task_metadata


def records(task):
    path = task.persistent_dir / "history.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


@pytest.mark.parametrize("kind", list(TaskType))
def test_all_task_types_append_one_terminal_metadata_record(tmp_path, kind):
    class Task(DemoTask):
        task_type = kind

        def initialize(self):
            self.persist_metadata()
            self.persist_metadata()
            assert not (self.persistent_dir / "history.jsonl").exists()
            super().initialize()

    task = Task({"task_name": "fixed", "x": 2, "y": 3}, workspace_path=tmp_path, reg_name="example")
    status = TaskExecutor().execute(task)
    history = records(task)
    assert history == [status.model_dump(mode="json")]
    assert datetime.fromisoformat(history[0]["started_at"]) == status.started_at
    assert history[0]["state"] == "succeeded"
    assert history[-1]["input_params"]["x"] == 2
    assert history[-1]["output_params"]["result"] == 5


def test_replacement_preserves_history_and_rejected_start_does_not_append(tmp_path):
    class Task(DemoTask):
        def initialize(self):
            before = records(self)
            with pytest.raises(FileExistsError, match="Task is running"):
                TaskExecutor().execute(
                    DemoTask(self.input_params.model_dump(), workspace_path=tmp_path, reg_name="demo")
                )
            assert records(self) == before
            super().initialize()

    first = Task({"task_name": "fixed", "x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo")
    TaskExecutor().execute(first)
    second = DemoTask({"task_name": "fixed", "x": 10, "y": 20}, workspace_path=tmp_path, reg_name="demo")
    TaskExecutor().execute(second)
    history = records(second)
    assert len(history) == 2
    assert [row["output_params"]["result"] for row in history] == [3, 30]
    assert history[0]["started_at"] != history[1]["started_at"]
    assert set(path.name for path in tmp_path.iterdir()) == {"tasks"}


def test_failed_execution_and_children_use_the_same_history_format(tmp_path):
    class Failed(DemoTask):
        def initialize(self):
            raise ValueError("invalid source")

    class Parent(DemoTask):
        def initialize(self):
            self.run_task("failed", task_name="child", x=1, y=2)

    task = Parent({"task_name": "parent", "x": 1, "y": 2}, workspace_path=tmp_path, reg_name="parent")
    with pytest.raises(Exception, match="invalid source"):
        TaskExecutor(resolve_task=lambda _: Failed).execute(task)
    for path in tmp_path.rglob("history.jsonl"):
        history = [json.loads(line) for line in path.read_text().splitlines()]
        assert len(history) == 1
        assert history[-1]["state"] == "failed"
        assert "invalid source" in history[-1]["error"]
    assert len(list(tmp_path.rglob("history.jsonl"))) == 2


def test_jsonl_recovers_incomplete_tail_and_serializes_concurrent_appends(tmp_path):
    path = tmp_path / "history.jsonl"
    journal = TaskJournal(path)
    journal.append({"first": True})
    with path.open("ab") as handle:
        handle.write(b'{"interrupted":')
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda number: journal.append({"number": number}), range(32)))
    history = [json.loads(line) for line in path.read_text().splitlines()]
    assert history[0] == {"first": True}
    assert sorted(row["number"] for row in history[1:]) == list(range(32))


def test_reconciled_execution_appends_one_terminal_record(tmp_path, monkeypatch):
    task = DemoTask({"task_name": "fixed", "x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo")
    status = TaskExecutor().execute(task)
    interrupted = status.model_copy(
        update={
            "state": TaskState.RUNNING,
            "started_at": status.started_at + timedelta(seconds=1),
            "finished_at": None,
            "output_params": {},
        }
    )
    write_task_metadata(task.task_dir, interrupted)
    monkeypatch.setattr(lifecycle, "process_instance", lambda *_: None)
    repaired = lifecycle.reconcile_task(task.task_dir, interrupted.started_at)
    assert records(task) == [status.model_dump(mode="json"), repaired.model_dump(mode="json")]
    assert repaired.state == TaskState.FAILED
    lifecycle.reconcile_task(task.task_dir, interrupted.started_at)
    assert len(records(task)) == 2


def test_repeated_terminal_publication_does_not_duplicate_history(tmp_path):
    task = DemoTask({"task_name": "fixed", "x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo")
    status = TaskExecutor().execute(task)
    directory = tmp_path / "publication"
    progress = TaskProgress(directory, status)
    progress.publish()
    progress.publish()
    history = (directory / "persistent/history.jsonl").read_text().splitlines()
    assert [json.loads(line) for line in history] == [status.model_dump(mode="json")]


def test_task_execution_uses_file_locks_when_directory_locks_are_unsupported(tmp_path, monkeypatch):
    flock = fcntl.flock

    def files_only(handle, operation):
        descriptor = handle if isinstance(handle, int) else handle.fileno()
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("Directory locking is unsupported")
        return flock(handle, operation)

    monkeypatch.setattr(fcntl, "flock", files_only)
    task = DemoTask({"task_name": "fixed", "x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo")
    TaskExecutor().execute(task)
    assert records(task)[-1]["output_params"]["result"] == 3
