"""Incremental Task metadata polling and subscription contracts."""

import asyncio
import os
import shutil
import threading
from unittest.mock import Mock

import pytest

from axonx.app.components.task_repository import LocalTaskRepository, TaskChanges, TaskChangeSubscription
from axonx.app.components.task_repository.local import index
from axonx.app.core import Application
from axonx.task.enums import TaskState, TaskType
from axonx.task.schemas.lifecycle import TaskMetadata
from axonx.task.storage.workspace import task_path, write_task_metadata


@pytest.fixture
def repository(tmp_path):
    app = Application(
        workspace_dir=str(tmp_path),
        log_to_console=False,
        log_to_file=False,
        components={"task_repository": {"default": {"backend": "local", "poll_interval": 0.01}}},
    )
    return app.context.components["task_repository"]["default"]


def persist(root, name="one", run_id="run-one"):
    metadata = TaskMetadata(version=1, task_id=f"base#demo#{name}", task_type=TaskType.BASE, run_id=run_id)
    directory = task_path(root, metadata.task_id)
    directory.mkdir(parents=True, exist_ok=True)
    write_task_metadata(directory, metadata)
    return metadata


@pytest.mark.parametrize("interval", [0, -1, float("inf"), float("nan")])
def test_poll_interval_must_be_positive_and_finite(interval):
    with pytest.raises(ValueError, match="poll_interval"):
        LocalTaskRepository(poll_interval=interval)


async def test_start_reads_each_record_once_and_background_catches_startup_changes(repository, monkeypatch):
    original = persist(repository.root)
    read = Mock(wraps=index.read_task_metadata)
    monkeypatch.setattr(index, "read_task_metadata", read)
    async with repository:
        assert read.call_count == 1
        # Replace a record before the background task has had a chance to run.
        changed = persist(repository.root, run_id="run-two")
        subscription = repository.subscribe()
        assert await asyncio.wait_for(anext(subscription), 2) == TaskChanges(frozenset({original.task_id}))
        assert await repository.entry(original.task_id) == changed
        assert read.call_count == 2
        await repository._refresh()
        assert read.call_count == 2


async def test_poll_detects_external_create_update_and_delete(repository):
    async with repository:
        subscription = repository.subscribe()
        metadata = persist(repository.root)
        assert await asyncio.wait_for(anext(subscription), 2) == TaskChanges(frozenset({metadata.task_id}))
        updated = metadata.model_copy(update={"state": TaskState.SUCCEEDED})
        write_task_metadata(task_path(repository.root, metadata.task_id), updated)
        await asyncio.wait_for(anext(subscription), 2)
        assert await repository.entry(metadata.task_id) == updated
        shutil.rmtree(task_path(repository.root, metadata.task_id))
        await asyncio.wait_for(anext(subscription), 2)
        assert await repository.entries() == {}


async def test_poll_ignores_artifacts_and_reads_no_unchanged_metadata(repository, monkeypatch):
    metadata = persist(repository.root)
    await repository.reconcile()
    artifact = task_path(repository.root, metadata.task_id) / "artifacts"
    artifact.mkdir()
    (artifact / "large.parquet").write_bytes(b"payload")
    # Neither stat nor open should ever reach artifact descendants.
    scandir = os.scandir

    def shallow_scan(path):
        assert path.parent == repository.root
        return scandir(path)

    monkeypatch.setattr(index.os, "scandir", shallow_scan)
    monkeypatch.setattr(index, "read_task_metadata", Mock(side_effect=AssertionError("unchanged record read")))
    assert await repository._refresh() == TaskChanges()
    (artifact / "large.parquet").write_bytes(b"updated")
    assert await repository._refresh() == TaskChanges()


async def test_atomic_same_size_replacement_with_preserved_mtime_is_detected(repository):
    metadata = persist(repository.root)
    await repository.reconcile()
    path = task_path(repository.root, metadata.task_id) / "metadata.json"
    before = path.stat()
    changed = persist(repository.root, run_id="run-two")
    assert path.stat().st_size == before.st_size
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert await repository._refresh() == TaskChanges(frozenset({metadata.task_id}))
    assert await repository.entry(metadata.task_id) == changed


async def test_invalid_record_is_retained_retried_and_eventually_deleted(repository):
    metadata = persist(repository.root)
    await repository.reconcile()
    path = task_path(repository.root, metadata.task_id) / "metadata.json"
    path.write_text("{")
    assert await repository._refresh() == TaskChanges()
    assert await repository.entry(metadata.task_id) == metadata
    changed = persist(repository.root, run_id="run-two")
    assert await repository._refresh() == TaskChanges(frozenset({metadata.task_id}))
    assert await repository.entry(metadata.task_id) == changed
    path.unlink()
    assert await repository._refresh() == TaskChanges(frozenset({metadata.task_id}))
    assert await repository.entries() == {}


async def test_scan_error_retains_entire_index(repository, monkeypatch):
    first = persist(repository.root)
    second = persist(repository.root, name="two")
    await repository.reconcile()
    persist(repository.root, run_id="run-two")
    original = index.read_task_metadata

    def failed_read(directory, task_id, **kwargs):
        if task_id == second.task_id:
            raise PermissionError("temporary NAS failure")
        return original(directory, task_id, **kwargs)

    monkeypatch.setattr(index, "read_task_metadata", failed_read)
    with pytest.raises(PermissionError):
        await repository.reconcile()
    assert await repository.entries() == {first.task_id: first, second.task_id: second}


async def test_poll_retries_after_scan_failure(repository, monkeypatch):
    metadata = persist(repository.root)
    original = index.read_task_metadata
    async with repository:
        subscription = repository.subscribe()
        changed = persist(repository.root, run_id="run-two")
        read = Mock(side_effect=[PermissionError("temporary NAS failure"), changed])
        monkeypatch.setattr(index, "read_task_metadata", read)
        logger = Mock()
        monkeypatch.setattr(repository, "logger", logger)
        await asyncio.wait_for(anext(subscription), 2)
        assert await repository.entry(metadata.task_id) == changed
        assert read.call_count == 2
        logger.exception.assert_called_once()
        monkeypatch.setattr(index, "read_task_metadata", original)


async def test_poll_does_not_follow_symlinks(repository, tmp_path):
    outside = tmp_path / "outside"
    metadata = persist(outside)
    directory = task_path(repository.root, metadata.task_id)
    directory.parent.mkdir(exist_ok=True)
    directory.symlink_to(task_path(outside, metadata.task_id), target_is_directory=True)
    await repository.reconcile()
    assert await repository.entries() == {}
    directory.unlink()
    directory.mkdir()
    (directory / "metadata.json").symlink_to(task_path(outside, metadata.task_id) / "metadata.json")
    await repository.reconcile()
    assert await repository.entries() == {}
    shutil.rmtree(directory)
    directory.parent.rmdir()
    directory.parent.symlink_to(outside / "base", target_is_directory=True)
    await repository.reconcile()
    assert await repository.entries() == {}


async def test_close_waits_for_inflight_scan_and_restart_reloads(repository, monkeypatch):
    metadata = persist(repository.root)
    await repository.start()
    started = threading.Event()
    release = threading.Event()
    original = index.os.scandir

    def blocking_scan(path):
        started.set()
        assert release.wait(2)
        return original(path)

    monkeypatch.setattr(index.os, "scandir", blocking_scan)
    closing = None
    try:
        assert await asyncio.to_thread(started.wait, 2)
        closing = asyncio.create_task(repository.close())
        await asyncio.sleep(0.02)
        assert not closing.done()
    finally:
        release.set()
        if closing is None:
            await repository.close()
        else:
            await closing
    assert repository._watch_task is None
    assert not repository.is_started
    monkeypatch.setattr(index.os, "scandir", original)
    persist(repository.root, run_id="run-two")
    async with repository:
        assert (await repository.entry(metadata.task_id)).run_id == "run-two"


@pytest.mark.asyncio
async def test_subscription_coalesces_without_sharing_consumer_state():
    closed = []
    first = TaskChangeSubscription(closed.append)
    second = TaskChangeSubscription(closed.append)

    first.publish(TaskChanges(frozenset({"one"})))
    first.publish(TaskChanges(frozenset({"two"}), resync=True))
    second.publish(TaskChanges(frozenset({"three"})))

    assert await anext(first) == TaskChanges(
        task_ids=frozenset({"one", "two"}),
        resync=True,
    )
    assert await anext(second) == TaskChanges(task_ids=frozenset({"three"}))

    first.close()
    assert closed == [first]
    with pytest.raises(StopAsyncIteration):
        await anext(first)
