"""Source reconciliation, retry and authenticated display-replica transfers."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from axonx.app.components.client import HttpClient
from axonx.app.components.service import HttpService
from axonx.app.components.sync import LocalSyncComponent
from axonx.app.components.task_repository import TaskChanges, TaskChangeSubscription
from axonx.app.config import ApplicationConfig
from axonx.app.core import Application
from axonx.task.schemas.lifecycle import TaskMetadata
from axonx.task.storage.artifacts import artifact_record
from axonx.task.storage.workspace import task_path, write_task_metadata
from axonx.task.sync.index import snapshot_index, source_revision


class Repository:
    def __init__(self):
        self.changes = TaskChangeSubscription(lambda _: None)

    def subscribe(self):
        return self.changes


def task(root, task_id="etl#demo#research-core", state="succeeded", run_id="first"):
    directory = task_path(root, task_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "result.txt").write_text("result")
    write_task_metadata(
        directory,
        TaskMetadata(
            machine_id="test-machine",
            pid=99999999,
            process_started_at="2026-01-01T00:00:00Z",
            version=1,
            task_id=task_id,
            task_type=task_id.split("#", 1)[0],
            run_id=run_id,
            state=state,
            output_params={"artifacts": {"result": artifact_record(directory / "result.txt", directory)}},
        ),
    )
    return directory


def sync_component(root, monkeypatch, remote=None, budget=512 * 1024 * 1024):
    sync = LocalSyncComponent(target="http://remote:1024", task_names=["research-core"])
    sync.root = root
    sync.app_context = SimpleNamespace(
        app_config=ApplicationConfig(transfer_budget_bytes=budget, targets=[{"address": "http://remote:1024"}])
    )
    sync.repository = Repository()
    sync._needs_reconcile = False
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.run_job.return_value = SimpleNamespace(
        success=True, answer={"transfer_budget_bytes": budget, "tasks": remote or {}}
    )
    monkeypatch.setattr(sync, "_client", lambda: client)
    return sync, client


@pytest.mark.parametrize("kind", ["etl", "train", "inference", "backtest", "composite"])
def test_filter_matches_only_exact_task_name(kind):
    sync = LocalSyncComponent(target="remote:1024", task_names=["research-v1", "research-v2"])
    assert sync._should_sync(f"{kind}#any_registration#research-v1")
    assert not sync._should_sync(f"{kind}#research-v1#other")
    assert not sync._should_sync(f"{kind}#any_registration#research-v10")


@pytest.mark.parametrize("names", ["research-v1", [""], [None], ["bad_name"], {"name": "research-v1"}])
def test_invalid_filters_are_rejected(names):
    with pytest.raises(ValueError, match="task_names"):
        LocalSyncComponent(target="remote:1024", task_names=names)


@pytest.mark.parametrize(
    "option",
    [
        "task_ids",
        "task_id_prefixes",
        "sync_on_start",
        "max_file_bytes",
        "max_archive_bytes",
    ],
)
def test_removed_options_fail(option):
    with pytest.raises(ValueError, match="Removed sync options"):
        LocalSyncComponent(target="remote:1024", **{option: []})


@pytest.mark.asyncio
async def test_reconciliation_recovers_after_remote_startup_failure(tmp_path, monkeypatch):
    task(tmp_path)
    sync, client = sync_component(tmp_path, monkeypatch)
    client.run_job.side_effect = [
        ConnectionError("offline"),
        client.run_job.return_value,
    ]
    sync._send = AsyncMock()
    async with sync:
        client.run_job.assert_not_awaited()
        assert sync._needs_reconcile
        assert not (await sync.flush()).uploaded
        assert sync._needs_reconcile
        assert (await sync.flush()).uploaded == ["etl/etl#demo#research-core"]
        assert not sync._needs_reconcile
        assert client.run_job.await_count == 2


@pytest.mark.asyncio
async def test_terminal_event_sends_but_running_and_deletion_do_not(tmp_path, monkeypatch):
    task_id = "etl#demo#research-core"
    directory = task(tmp_path, state="running")
    sync, _ = sync_component(tmp_path, monkeypatch)
    sync._send = AsyncMock()
    async with sync:
        sync._pending.add(task_id)
        assert not (await sync.flush()).uploaded
        task(tmp_path)
        sync.repository.changes.publish(TaskChanges(frozenset({task_id})))
        await asyncio.sleep(0)
        assert (await sync.flush()).uploaded == [f"etl/{task_id}"]
        (directory / "metadata.json").unlink()
        sync._pending.add(task_id)
        assert not (await sync.flush()).uploaded
        assert sync._send.await_count == 1


@pytest.mark.asyncio
async def test_failed_batch_is_retried_and_deferred_tasks_remain_queued(tmp_path, monkeypatch):
    ids = [f"etl#demo{i}#research-core" for i in range(3)]
    for task_id in ids:
        task(tmp_path, task_id)
    sync, _ = sync_component(tmp_path, monkeypatch, budget=17 * 1024)
    sync.max_archives_per_flush = 2
    sync._pending.update(ids)
    sync._send = AsyncMock(side_effect=[ConnectionError("offline"), None, None, None])
    report = await sync.flush()
    assert report.uploaded == [f"etl/{ids[1]}"]
    assert set(report.deferred) == {f"etl/{ids[0]}", f"etl/{ids[2]}"}
    assert sync._pending == {ids[0], ids[2]}
    assert set((await sync.flush()).uploaded) == {f"etl/{ids[0]}", f"etl/{ids[2]}"}
    assert not sync._pending


@pytest.mark.asyncio
async def test_deterministic_budget_failure_is_reported_without_retry(tmp_path, monkeypatch):
    task_id = "etl#demo#research-core"
    task(tmp_path)
    sync, _ = sync_component(tmp_path, monkeypatch, budget=1)
    sync._pending.add(task_id)
    report = await sync.flush()
    assert report.rejected == [f"etl/{task_id}"]
    assert not sync._pending
    assert not list(tmp_path.glob("axonx-display-*"))


@pytest.mark.asyncio
async def test_authenticated_roundtrip_reconciles_reruns_and_skips_replicas(tmp_path, monkeypatch):
    source, remote = tmp_path / "source", tmp_path / "remote"
    source.mkdir()
    remote.mkdir()
    ids = [
        "etl#demo#research-core",
        "train#demo#research-core",
        "composite#demo#research-core",
    ]
    for task_id in ids:
        directory = task(source, task_id)
        (directory / "inputs").mkdir()
        (directory / "inputs/large.bin").write_bytes(b"not transferred")
    app = Application(
        workspace_dir=str(remote),
        transfer_budget_bytes=64 * 1024,
        enable_logo=False,
        log_to_console=False,
        log_to_file=False,
        components={"task_repository": {"default": {"backend": "local"}}},
        jobs={
            "task_sync_index": {"steps": [{"backend": "task_sync_index_step"}]},
            "sync_tasks": {"steps": [{"backend": "sync_tasks_step"}]},
        },
    )
    server = HttpService(token="secret", web_enabled=False).build_service(app)
    sync, _ = sync_component(source, monkeypatch, budget=128 * 1024)
    monkeypatch.setattr(
        sync,
        "_client",
        lambda: HttpClient(
            target="http://remote:1024",
            token="secret",
            transport=httpx.ASGITransport(app=server),
        ),
    )
    async with server.router.lifespan_context(server):
        await sync._reconcile()
        assert sync.budget == 64 * 1024
        report = await sync.flush()
        assert set(report.uploaded) == {f"{task_id.split('#', maxsplit=1)[0]}/{task_id}" for task_id in ids}
        assert all(not (task_path(remote, task_id) / "inputs").exists() for task_id in ids)
        remote_index = snapshot_index(remote, frozenset())
        assert all(remote_index[task_id]["source_revision"] == source_revision(source, task_id) for task_id in ids)
        await sync._reconcile()
        assert not sync._pending
        task(source, ids[0], run_id="second")
        await sync._reconcile()
        assert sync._pending == {ids[0]}
        await sync.flush()
        assert snapshot_index(remote, frozenset())[ids[0]]["source_revision"] == source_revision(source, ids[0])
        reverse, _ = sync_component(remote, monkeypatch)
        await reverse._reconcile()
        assert not reverse._pending
        assert not list(source.glob("axonx-display-*"))


@pytest.mark.asyncio
@pytest.mark.parametrize("cancellations", [1, 2])
async def test_cancelled_blocking_work_finishes_before_resource_cleanup(cancellations):
    import threading

    from axonx.common.async_work import run_blocking

    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def work():
        entered.set()
        release.wait(timeout=5)
        finished.set()

    operation = asyncio.create_task(run_blocking(work))
    assert await asyncio.to_thread(entered.wait, 2)
    for _ in range(cancellations):
        operation.cancel()
        await asyncio.sleep(0)
    assert not operation.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert finished.is_set()


@pytest.mark.asyncio
async def test_settling_failure_preserves_the_pending_queue(tmp_path, monkeypatch):
    task_id = "etl#demo#research-core"
    task(tmp_path)
    sync, _ = sync_component(tmp_path, monkeypatch)
    sync._pending.add(task_id)

    def fail(_pending):
        raise OSError("metadata temporarily unavailable")

    monkeypatch.setattr(sync, "_settled", fail)
    with pytest.raises(OSError, match="temporarily unavailable"):
        await sync.flush()
    assert sync._pending == {task_id}


@pytest.mark.asyncio
async def test_resync_requested_during_reconciliation_is_preserved(tmp_path, monkeypatch):
    sync, _ = sync_component(tmp_path, monkeypatch)

    def changed(_remote):
        sync._needs_reconcile = True
        return set()

    monkeypatch.setattr(sync, "_missing", changed)
    await sync._reconcile()
    assert sync._needs_reconcile


@pytest.mark.asyncio
async def test_live_flush_refreshes_remote_without_rescanning_terminal_sources(tmp_path, monkeypatch):
    sync, client = sync_component(tmp_path, monkeypatch)
    sync.live_task_ids = frozenset({"composite#demo#research-core"})
    sync._missing = lambda _: pytest.fail("Unchanged terminal sources were rescanned")
    sync._transfer = AsyncMock()
    await sync.flush()
    client.run_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_archive_quota_bounds_preparation_work(tmp_path, monkeypatch):
    from axonx.app.components.sync import local

    identities = [f"etl#demo{i}#research-core" for i in range(10)]
    for identity in identities:
        directory = task(tmp_path, identity)
        (directory / "result.txt").write_text("x" * 5000)
    sync, _ = sync_component(tmp_path, monkeypatch, budget=17 * 1024)
    sync.max_archives_per_flush = 1
    sync._pending.update(identities)
    sync._send = AsyncMock()
    prepared = []
    original = local.prepare_replica

    def prepare(*args, **kwargs):
        prepared.append(args[1])
        return original(*args, **kwargs)

    monkeypatch.setattr(local, "prepare_replica", prepare)
    report = await sync.flush()
    assert len(prepared) < len(identities)
    assert report.archives == 1
    assert set(report.uploaded + report.deferred) == {f"etl/{identity}" for identity in identities}
    assert set(identities) - set(prepared) <= sync._pending
