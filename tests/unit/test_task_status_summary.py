"""List summaries remain small without changing full snapshots or stored records."""

from datetime import UTC, datetime
from importlib.resources import files
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import yaml

from axonx.components.service import HttpService
from axonx.components.task_manager.local.manager import LocalTaskManager
from axonx.components.task_repository import LocalTaskRepository
from axonx.core import Application
from axonx.task.query.summary import summarize_status
from axonx.task.storage.workspace import TaskMetadata, TaskStepStatus


def status():
    return TaskMetadata(
        version=1,
        task_id="analysis#test#summary",
        run_id="run",
        task_type="analysis",
        report_kind="online",
        input_params={
            "task_name": "friendly",
            "comparison_keys": [],
            "large": "x" * 100000,
        },
        output_params={"comparisons": [], "large": "x" * 100000},
        steps=[
            TaskStepStatus(name="done", finished_at=datetime.now(UTC), percentage=100),
            TaskStepStatus(name="active", percentage=42),
            TaskStepStatus(name="next"),
        ],
        error="x" * 2000,
    )


def test_summary_preserves_progress_and_bounds_large_fields():
    task = status()
    summary = summarize_status(task)
    assert not {"input_params", "output_params", "steps", "children"} & summary.model_fields_set
    assert summary.display_name == "friendly"
    assert summary.is_online is True
    assert summary.step_progress.model_dump() == {
        "current": 2,
        "total": 3,
        "name": "active",
        "percentage": 42,
    }
    assert len(summary.error) == 1000
    assert len(task.error) == 2000
    task.steps = []
    assert summarize_status(task).step_progress is None
    task.steps = [TaskStepStatus(name="finished", finished_at=datetime.now(UTC), percentage=100)]
    assert summarize_status(task).step_progress.current == 1


async def test_local_summary_avoids_full_snapshot_copy(tmp_path, monkeypatch):
    task = status()
    repository = LocalTaskRepository(
        app_context=SimpleNamespace(app_config=SimpleNamespace(workspace_dir=str(tmp_path)))
    )
    older = task.model_copy(update={"task_id": "analysis#test#older"}, deep=True)
    task.created_at = datetime.now(UTC)
    repository._entries = {older.task_id: older, task.task_id: task}

    def refuse_copy(*_args, **_kwargs):
        raise AssertionError("Summary projection must not deep-copy full metadata")

    monkeypatch.setattr(TaskMetadata, "model_copy", refuse_copy)
    manager = object.__new__(LocalTaskManager)
    manager._supervisor = SimpleNamespace(run_pids={})
    manager.repository = repository
    manager.list_statuses = AsyncMock(side_effect=AssertionError("Full list must not be copied"))
    summaries = await manager.list_summaries()
    assert summaries == [summarize_status(task), summarize_status(older)]
    summaries[0].step_progress.name = "changed"
    assert (await manager.list_summaries())[0].step_progress.name == "active"


async def test_job_defaults_to_full_and_validates_detail(tmp_path):
    app = Application(
        workspace_dir=str(tmp_path),
        enable_logo=False,
        log_to_console=False,
        log_to_file=False,
        components={
            "task_repository": {"default": {"backend": "local"}},
            "task_manager": {"default": {"backend": "local"}},
        },
        jobs={
            "list_task_statuses": yaml.safe_load(files("axonx.config").joinpath("default.yaml").read_text())["jobs"][
                "list_task_statuses"
            ]
        },
    )
    async with app:
        manager = next(iter(app.context.components["task_manager"].values()))
        task = status()
        manager.list_statuses = AsyncMock(return_value=[task])
        manager.list_summaries = AsyncMock(return_value=[summarize_status(task)])
        full = await app.run_job("list_task_statuses")
        assert full.success
        assert full.answer == [task]
        explicit = await app.run_job("list_task_statuses", {"detail": "full"})
        assert explicit.answer == full.answer
        summary = await app.run_job("list_task_statuses", {"detail": "summary"})
        assert summary.success
        assert summary.answer == [summarize_status(task)]
        server = HttpService(web_enabled=False, token="test-token").build_service(app)
        async with httpx.AsyncClient(
            base_url="http://test",
            transport=httpx.ASGITransport(app=server),
            headers={"Authorization": "Bearer test-token"},
        ) as client:
            response = await client.post("/jobs/list_task_statuses", json={"arguments": {"detail": "summary"}})
            assert response.status_code == 200
            item = response.json()["answer"][0]
            assert item["task_type"] == "analysis"
            assert item["step_progress"]["current"] == 2
            assert "output_params" not in item
            full_response = await client.post("/jobs/list_task_statuses", json={"arguments": {}})
            assert full_response.json()["answer"][0]["output_params"] == task.output_params
            invalid = await client.post("/jobs/list_task_statuses", json={"arguments": {"detail": "invalid"}})
            assert invalid.status_code == 422
        with pytest.raises(ValueError, match="detail"):
            await app.run_job("list_task_statuses", {"detail": "invalid"})


async def test_filtered_index_copies_only_matching_results(tmp_path, monkeypatch):
    selected = status()
    selected.state = "succeeded"
    excluded = selected.model_copy(update={"task_id": "train#large#excluded", "task_type": "train"}, deep=True)
    repository = LocalTaskRepository(
        app_context=SimpleNamespace(app_config=SimpleNamespace(workspace_dir=str(tmp_path)))
    )
    repository._entries = {selected.task_id: selected, excluded.task_id: excluded}
    original_copy = TaskMetadata.model_copy
    copied = []

    def track_copy(record, **kwargs):
        assert record.task_id == selected.task_id, "Excluded outputs must never be copied"
        copied.append(record.task_id)
        return original_copy(record, **kwargs)

    monkeypatch.setattr(TaskMetadata, "model_copy", track_copy)
    result = await repository.entries(task_type="analysis", state="succeeded")
    assert copied == [selected.task_id]
    result[selected.task_id].output_params["comparisons"].append("consumer mutation")
    assert selected.output_params["comparisons"] == []
    assert [item.task_id for item in await repository.summaries(task_type="analysis", state="succeeded")] == [
        selected.task_id
    ]


async def test_graph_projects_under_repository_lock_without_copying_outputs(tmp_path, monkeypatch):
    task = status()
    repository = LocalTaskRepository(
        app_context=SimpleNamespace(app_config=SimpleNamespace(workspace_dir=str(tmp_path)))
    )
    repository._entries = {task.task_id: task}

    def refuse_copy(*_args, **_kwargs):
        raise AssertionError("Graph queries must not copy complete task records")

    monkeypatch.setattr(TaskMetadata, "model_copy", refuse_copy)
    manager = object.__new__(LocalTaskManager)
    manager.repository = repository
    graph = await manager.get_graph(task.task_id)
    assert graph.nodes[0].task_id == task.task_id
    graph.nodes[0].parent_ids.append("consumer mutation")
    assert (await manager.get_graph(task.task_id)).nodes[0].parent_ids == []


def test_nightly_pipeline_is_discoverable_in_online_workbench():
    task = status()
    task.report_kind = "compare_pipeline"
    summary = summarize_status(task)
    assert summary.is_online and summary.report_kind == "compare_pipeline"
