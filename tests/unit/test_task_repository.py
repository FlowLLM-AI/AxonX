"""Task repository watcher and subscription contracts."""

import asyncio
from unittest.mock import Mock

import pytest

from axonx.components.task_repository import (
    LocalTaskRepository,
    TaskChanges,
    TaskChangeSubscription,
)
from axonx.components.task_repository.local.watcher import TaskWorkspaceWatcher


def test_repository_collects_watch_options():
    repository = LocalTaskRepository(debounce=250, poll_delay_ms=50)

    assert repository._watcher.options == {
        "recursive": True,
        "force_polling": True,
        "debounce": 250,
        "step": 3_000,
        "poll_delay_ms": 50,
    }


@pytest.mark.asyncio
async def test_watcher_recovers_after_failed_pump(tmp_path, monkeypatch):
    recovered = asyncio.Event()
    changes = []
    attempts = 0

    async def handler(change):
        changes.append(change)
        recovered.set()

    async def pump():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ExceptionGroup("watcher failed", [OSError(40, "Too many levels of symbolic links")])
        await asyncio.Event().wait()

    logger = Mock()
    watcher = TaskWorkspaceWatcher(tmp_path, {}, handler, logger)
    monkeypatch.setattr(watcher, "_pump", pump)
    task = asyncio.create_task(watcher.run())
    try:
        await asyncio.wait_for(recovered.wait(), timeout=3)
        assert attempts == 2
        assert changes == [TaskChanges(resync=True)]
        assert not task.done()
        logger.exception.assert_called_once()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


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
