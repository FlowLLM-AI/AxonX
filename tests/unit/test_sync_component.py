from types import SimpleNamespace

import pytest

from axonx.components.sync import LocalSyncComponent, SyncReport


class Repository:
    def __init__(self, task_ids):
        self.task_ids = task_ids

    async def entries(self):
        return dict.fromkeys(self.task_ids)


@pytest.mark.asyncio
async def test_sync_filters_pending_tasks_and_deletions(tmp_path):
    exact = "etl#exact#run#1234567890"
    prefixed = "etl#group#run#1234567890"
    excluded = "etl#other#run#1234567890"
    removed = "etl#group#old#1234567890"
    removed_excluded = "etl#other#old#1234567890"
    sync = LocalSyncComponent(
        remote_ip="127.0.0.1",
        task_ids=[exact],
        task_id_prefixes=["etl#group#"],
    )
    sync.root = tmp_path
    sync.repository = Repository([exact, prefixed, excluded])
    sync._pending = {exact, prefixed, excluded}
    sync._acknowledged = {removed, removed_excluded}
    sync._state = SimpleNamespace(save=lambda _: None)
    sync._settled = lambda task_ids: list(task_ids)
    captured = None

    async def transfer(pending, deletions):
        nonlocal captured
        captured = (pending, deletions)
        return SyncReport()

    sync._transfer = transfer

    await sync.flush()

    assert captured == ([exact, prefixed], [f"etl/{removed}"])


def test_empty_sync_filters_include_every_task():
    sync = LocalSyncComponent(remote_ip="127.0.0.1", task_ids=[], task_id_prefixes=[])

    assert sync._should_sync("etl#any#run#1234567890")
