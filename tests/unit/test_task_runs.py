"""Every Task type preserves execution metadata across replacements and failures."""

import fcntl
import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from axonx.task.builtins.demo import DemoTask
from axonx.task.models.identity import TaskType
from axonx.task.runtime.executor import TaskExecutor
from axonx.task.storage.logs import TaskJournal


def records(task):
    return [json.loads(line) for line in (task.persistent_dir / "runs.jsonl").read_text().splitlines()]


@pytest.mark.parametrize("kind", list(TaskType))
def test_all_task_types_append_started_and_finished_records(tmp_path, kind):
    class Task(DemoTask):
        task_type = kind

    task = Task({"task_name": "fixed", "x": 2, "y": 3}, workspace_path=tmp_path, reg_name="example")
    status = TaskExecutor().execute(task)
    history = records(task)
    assert [row["event"] for row in history] == ["started", "finished"]
    assert all(row["task_id"] == status.task_id for row in history)
    assert all(datetime.fromisoformat(row["started_at"]) == status.started_at for row in history)
    assert [row["state"] for row in history] == ["running", "succeeded"]
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
    assert [row["event"] for row in history] == ["started", "finished", "started", "finished"]
    assert [history[index]["output_params"]["result"] for index in (1, 3)] == [3, 30]
    assert history[1]["started_at"] != history[3]["started_at"]
    assert history[2]["previous_started_at"] == history[1]["started_at"]
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
    for path in tmp_path.rglob("runs.jsonl"):
        history = [json.loads(line) for line in path.read_text().splitlines()]
        assert [row["event"] for row in history] == ["started", "finished"]
        assert history[-1]["state"] == "failed"
        assert "invalid source" in history[-1]["error"]
    assert len(list(tmp_path.rglob("runs.jsonl"))) == 2


def test_jsonl_recovers_incomplete_tail_and_serializes_concurrent_appends(tmp_path):
    path = tmp_path / "runs.jsonl"
    journal = TaskJournal(path)
    journal.append({"first": True})
    with path.open("ab") as handle:
        handle.write(b'{"interrupted":')
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda number: journal.append({"number": number}), range(32)))
    history = [json.loads(line) for line in path.read_text().splitlines()]
    assert history[0] == {"first": True}
    assert sorted(row["number"] for row in history[1:]) == list(range(32))


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
