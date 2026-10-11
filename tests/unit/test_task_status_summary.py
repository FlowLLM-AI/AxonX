"""List summaries remain small without changing full snapshots or stored records."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from importlib.resources import files

import httpx
import pytest
import yaml

from axonx.components.task_manager.local.manager import LocalTaskManager
from axonx.core import Application
from axonx.components.service import HttpService
from axonx.task.query.summary import summarize_status
from axonx.task.storage.workspace import TaskStatus, TaskStepStatus


def status():
    return TaskStatus(
        task_id="analysis#test#summary",
        run_id="run",
        task_type="analysis",
        config={"task_name": "friendly", "comparison_keys": [], "large": "x" * 100000},
        result={"comparisons": [], "large": "x" * 100000},
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
    assert not {"config", "result", "steps"} & summary.keys()
    assert summary["display_name"] == "friendly"
    assert summary["is_online"] is True
    assert summary["step_progress"] == {"current": 2, "total": 3, "name": "active", "percentage": 42}
    assert len(summary["error"]) == 1000
    assert len(task.error) == 2000
    task.steps = []
    assert summarize_status(task)["step_progress"] is None
    task.steps = [TaskStepStatus(name="finished", finished_at=datetime.now(UTC), percentage=100)]
    assert summarize_status(task)["step_progress"]["current"] == 1


async def test_local_summary_avoids_full_snapshot_copy():
    task = status()
    manager = object.__new__(LocalTaskManager)
    manager.repository = AsyncMock()
    manager.repository.statuses.return_value = {task.task_id: task}
    manager.list_statuses = AsyncMock(side_effect=AssertionError("Full list must not be copied"))
    assert await manager.list_summaries() == [summarize_status(task)]


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
            assert "result" not in item
            full_response = await client.post("/jobs/list_task_statuses", json={"arguments": {}})
            assert full_response.json()["answer"][0]["result"] == task.result
            invalid = await client.post("/jobs/list_task_statuses", json={"arguments": {"detail": "invalid"}})
            assert invalid.status_code == 422
        with pytest.raises(ValueError, match="detail"):
            await app.run_job("list_task_statuses", {"detail": "invalid"})
