"""Shared records are observable; only supervised Runs are controllable."""

import pytest

from axonx.app.core import Application
from axonx.task.runtime.process import machine_id
from axonx.task.schemas.lifecycle import TaskMetadata
from axonx.task.storage.workspace import read_entry, task_path, write_task_metadata
from axonx.app.workspace.browser import delete_workspace_entries


def application(root, port=1024):
    return Application(
        workspace_dir=str(root),
        log_dir=str(root / "logs"),
        enable_logo=False,
        log_to_console=False,
        log_to_file=False,
        components={
            "task_repository": {"default": {"backend": "local"}},
            "updater": {"default": {"backend": "local"}},
        },
        jobs={"heartbeat": {"steps": []}},
        service={"backend": "http", "port": port, "web_enabled": False},
    )


def record(root, name, **kwargs):
    kwargs.setdefault("machine_id", machine_id())
    status = TaskMetadata(version=1, task_id=f"base#demo#{name}", run_id=name, task_type="base", **kwargs)
    directory = task_path(root, status.task_id)
    directory.mkdir(parents=True)
    write_task_metadata(directory, status)
    return status


@pytest.mark.parametrize("path", ["base", "base/base#demo#active", "base/base#demo#active/metadata.json"])
def test_workspace_delete_protects_active_tasks_and_ancestors(tmp_path, path):
    status = record(tmp_path, "active", state="running")
    with pytest.raises(ValueError, match="active Task"):
        delete_workspace_entries(tmp_path, [path])
    assert read_entry(tmp_path, status.task_id) == status


def test_old_task_lock_directory_is_no_longer_reserved(tmp_path):
    directory = tmp_path / ".locks"
    directory.mkdir()
    (directory / "workspace").write_text("old lock")
    assert delete_workspace_entries(tmp_path, [".locks"])[0].deleted == ".locks"
    assert not directory.exists()


async def test_shared_workspace_update_records_are_isolated(tmp_path):
    first, second = application(tmp_path), application(tmp_path, 1025)
    owner = first.context.components["updater"]["default"]
    observer = second.context.components["updater"]["default"]
    from axonx.daemon.update_worker import save

    folder = owner.directory / ("a" * 32)
    folder.mkdir(parents=True)
    save(folder / "record.json", {"phase": "building"})
    await observer.start()
    try:
        assert observer.status()["record"] is None
        assert owner.status()["record"]["phase"] == "building"
    finally:
        await observer.close()


async def test_update_status_does_not_adopt_old_unscoped_records(tmp_path):
    from axonx.daemon.update_worker import save

    update_id = "a" * 32
    folder = tmp_path / "updates" / update_id
    folder.mkdir(parents=True)
    save(folder / "record.json", {"phase": "building"})
    updater = application(tmp_path).context.components["updater"]["default"]
    assert updater.status()["record"] is None
    with pytest.raises(FileNotFoundError):
        updater.status(update_id)
