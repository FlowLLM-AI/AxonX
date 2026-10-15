"""Activity snapshots survive concurrent updates, replay and terminal cleanup."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from axonx.components.job.events import JOB_EVENT_ADAPTER
from axonx.enums import TaskState
from axonx.task import BaseTask, BaseOutputParams
from axonx.task.query.summary import summarize_status
from axonx.task.runtime.runner import TaskRunner
from axonx.task.storage.workspace import read_task_metadata


class ProgressTask(BaseTask):
    report_kind = "online_pipeline"

    def build_task_steps(self):
        yield self.download

    def download(self):
        def work(index):
            key = f"file:{index}"
            self.report_progress(name=key, label=key, state="running", completed=0, total=20)
            for completed in range(1, 21):
                self.report_progress(name=key, completed=completed)
            self.report_progress(name=key, state="done", files={"data": f"file-{index}.csv"})

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(work, range(8)))
        self.report_progress(name="future", state="waiting")

    def build_output_params(self):
        return BaseOutputParams()


def test_concurrent_substeps_are_durable_throttled_and_replayable(tmp_path):
    task = ProgressTask({}, workspace_path=tmp_path, reg_name="progress")
    status = TaskRunner().run(task)
    saved = read_task_metadata(task.task_dir, task.task_id)
    assert saved.steps == status.steps
    assert len(status.steps) == 10
    assert next(s for s in status.steps if s.name == "future").state == "skipped"
    assert all(a.completed == 20 and a.state == "done" for a in saved.steps if a.name.startswith("file:"))
    events = [
        JOB_EVENT_ADAPTER.validate_json(line) for line in (task.task_dir / "events.jsonl").read_text().splitlines()
    ]
    substeps = [event.model_dump(mode="json", exclude={"kind"}) for event in events if event.parent is not None]
    assert {a["name"]: a for a in substeps} == {
        a.name: a.model_dump(mode="json") for a in saved.steps if a.parent is not None
    }
    assert len(substeps) < 40  # Counter updates are coalesced; transitions remain immediate.
    assert {a["name"] for a in substeps if a["state"] == "done"} == {f"file:{i}" for i in range(8)}
    summary = summarize_status(status)
    assert summary.is_online and summary.report_kind == "online_pipeline"
    assert "steps" not in summary
    with pytest.raises(RuntimeError, match="TaskRunner"):
        task.report_progress(name="late", state="done")


def test_failure_settles_active_progress_and_keeps_completed_work(tmp_path):
    class Failed(ProgressTask):
        def download(self):
            self.report_progress(name="ready", state="done")
            self.report_progress(name="download", state="running")
            with pytest.raises(ValidationError):
                self.report_progress(name="download", completed=-1)
            raise ValueError("API failed")

    task = Failed({}, workspace_path=tmp_path, reg_name="failed")
    with pytest.raises(ValueError, match="API failed"):
        TaskRunner().run(task)
    status = read_task_metadata(task.task_dir, task.task_id)
    assert status.state == TaskState.FAILED
    assert next(s for s in status.steps if s.name == "ready").state == "done"
    assert next(s for s in status.steps if s.parent and s.name == "download").state == "failed"
    assert "API failed" in next(s for s in status.steps if s.parent and s.name == "download").error
    assert json.loads(task.metadata_path.read_text())["steps"][2]["finished_at"]


async def test_log_reads_are_bound_to_the_requested_run(tmp_path):
    from unittest.mock import AsyncMock
    from axonx.components.task_manager.local.manager import LocalTaskManager
    from axonx.task.storage.logs import TaskLogReader
    from axonx.task.storage.workspace import TaskMetadata

    log = tmp_path / "replacement.log"
    log.write_text("replacement-only")
    manager = object.__new__(LocalTaskManager)
    manager.app_context = None
    manager._logs = TaskLogReader(tmp_path)
    manager._status_of = AsyncMock(
        return_value=TaskMetadata(
            version=1,
            task_id="base#test#instance",
            run_id="replacement",
            task_type="base",
            log_path=str(log),
        )
    )
    with pytest.raises(ValueError, match="Task run changed"):
        await manager.read_log("base#test#instance", run_id="original")
    chunk = await manager.read_log("base#test#instance", run_id="replacement")
    assert chunk.content == "replacement-only"
