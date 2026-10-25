"""Operations navigation and categorized Task records."""

import pytest
from pydantic import ValidationError

from axonx.app.config import ApplicationConfig, resolve_app_config
from axonx.task.builtins.demo import DemoTask
from axonx.task.catalog.resolver import _task_definition
from axonx.task.enums import TaskCategory
from axonx.task.query.summary import summarize_status
from axonx.task.runtime.runner import TaskRunner
from axonx.task.storage.workspace import read_task_metadata


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
        {
            "title": {"en": "Sync", "zh": "同步"},
            "view": "schedules",
            "category": "comparison",
        },
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


def test_default_pages_group_tasks_by_category():
    config = ApplicationConfig.model_validate(resolve_app_config(log_config=False))
    assert "list_schedules" not in config.jobs
    assert list(config.studio.pages) == ["online", "comparison", "data"]
    assert config.studio.pages["data"].category == TaskCategory.DATA_UPDATE
    assert config.studio.pages["comparison"].category == TaskCategory.COMPARISON
