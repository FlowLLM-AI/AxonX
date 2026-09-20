"""Task repository watcher and subscription contracts."""

import pytest

from axonx.components.task_repository import (
    LocalTaskRepository,
    TaskChanges,
    TaskChangeSubscription,
)


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
