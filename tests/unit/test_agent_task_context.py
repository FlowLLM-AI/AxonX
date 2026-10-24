from datetime import UTC, datetime

import pytest

from axonx.core import Application
from axonx.enums import TaskState, TaskType
from axonx.task.storage.workspace import (
    TaskMetadata,
    task_path,
    write_task_metadata,
)


def _status(task_id: str, task_type: TaskType, sources=(), *, log_path=""):
    return TaskMetadata(
        version=1,
        task_id=task_id,
        run_id=f"run-{task_id}",
        task_type=task_type,
        reg_name="example",
        input_params={"source_tasks": ",".join(sources)},
        state=TaskState.RUNNING,
        created_at=datetime(2026, 9, 22, tzinfo=UTC),
        log_path=log_path,
    )


def _write_task_metadata(root, status):
    directory = task_path(root, status.task_id)
    directory.mkdir(parents=True)
    write_task_metadata(directory, status)
    return directory


@pytest.mark.asyncio
async def test_get_task_context_job_uses_repository_queries(tmp_path):
    grandparent = "base#native#prices"
    parent = "etl#native#clean"
    selected = "analysis#native#factor"
    child = "train#native#model"
    _write_task_metadata(tmp_path, _status(grandparent, TaskType.BASE))
    _write_task_metadata(tmp_path, _status(parent, TaskType.ETL, [grandparent]))
    selected_dir = _write_task_metadata(
        tmp_path,
        _status(selected, TaskType.ANALYSIS, [parent], log_path="/tmp/factor.log"),
    )
    _write_task_metadata(tmp_path, _status(child, TaskType.TRAIN, [selected]))
    metadata = _status(selected, TaskType.ANALYSIS, [parent], log_path="/tmp/factor.log")
    metadata.state = TaskState.SUCCEEDED
    metadata.reg_name = "factor"
    write_task_metadata(selected_dir, metadata)
    app = Application(
        workspace_dir=str(tmp_path),
        enable_logo=False,
        log_to_console=False,
        log_to_file=False,
        components={
            "task_repository": {"default": {"backend": "local"}},
        },
        jobs={
            "get_task_context": {
                "steps": [
                    {
                        "backend": "get_task_context_step",
                        "task_repository": "default",
                    }
                ]
            }
        },
    )

    async with app:
        response = await app.run_job("get_task_context", {"task_id": selected})

    payload = response.model_dump(mode="json")["answer"]
    assert response.success is True
    assert payload["task_id"] == selected
    assert payload["status"]["task_id"] == selected
    assert payload["metadata_exists"] is True
    assert payload["metadata_path"] == f"analysis/{selected}/metadata.json"
    assert payload["log_path"] == "/tmp/factor.log"
    assert payload["relations"]["direct_upstream"] == [parent]
    assert payload["relations"]["ancestors"] == [grandparent, parent]
    assert payload["relations"]["direct_downstream"] == [child]
