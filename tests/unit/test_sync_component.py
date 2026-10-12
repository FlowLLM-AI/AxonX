"""Stateless startup reconciliation and once-only batched transfers."""

import asyncio
import shutil
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from axonx.components.client import HttpClient
from axonx.components.service import HttpService
from axonx.components.sync import LocalSyncComponent
from axonx.components.task_repository import TaskChanges, TaskChangeSubscription
from axonx.config import ApplicationConfig
from axonx.core import Application
from axonx.task.storage.workspace import TaskMetadata, task_path, write_task_metadata
from axonx.task.sync import TaskArchiveApplier, build_archive, plan_task
from axonx.task.sync.index import snapshot_index


class Repository:
    def __init__(self):
        self.changes = TaskChangeSubscription(lambda _: None)

    def subscribe(self):
        return self.changes


def task(root, task_id="etl#demo#axon2-core", state="succeeded", run_id="first"):
    directory = task_path(root, task_id)
    directory.mkdir(parents=True, exist_ok=True)
    write_task_metadata(
        directory,
        TaskMetadata(version=1, task_id=task_id, task_type=task_id.split("#")[0], run_id=run_id, state=state),
    )
    (directory / "result.txt").write_text("result", encoding="utf-8")
    return directory


def sync_component(root, monkeypatch, remote):
    sync = LocalSyncComponent(target="http://remote:1024", task_names=["axon2-core"])
    sync.root = root
    sync.app_context = SimpleNamespace(app_config=ApplicationConfig(targets=[{"address": "http://remote:1024"}]))
    sync.repository = Repository()
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.run_job.return_value = SimpleNamespace(success=True, answer=remote)
    monkeypatch.setattr(sync, "_client", lambda: client)
    return sync, client


@pytest.mark.parametrize("kind", ["etl", "train", "inference", "backtest", "composite"])
def test_filter_matches_only_exact_task_name(kind):
    sync = LocalSyncComponent(target="remote:1024", task_names=["axon-v1", "axon-v2"])
    assert sync._should_sync(f"{kind}#any_registration#axon-v1")
    assert sync._should_sync(f"{kind}#any_registration#axon-v2")
    assert not sync._should_sync(f"{kind}#axon-v1#other")
    assert not sync._should_sync(f"{kind}#any_registration#axon-v10")


@pytest.mark.parametrize("names", ["axon-v1", [""], [None], ["bad_name"], {"name": "axon-v1"}])
def test_invalid_filters_are_rejected(names):
    with pytest.raises(ValueError, match="task_names"):
        LocalSyncComponent(target="remote:1024", task_names=names)


@pytest.mark.parametrize("option", ["task_ids", "task_id_prefixes", "sync_on_start"])
def test_removed_options_fail_instead_of_silently_syncing_all_tasks(option):
    with pytest.raises(ValueError, match="Removed sync options"):
        LocalSyncComponent(target="remote:1024", **{option: []})


def test_empty_filter_includes_all_names():
    assert LocalSyncComponent(target="remote:1024")._should_sync("etl#demo#any")


@pytest.mark.asyncio
async def test_startup_diff_detects_missing_rerun_and_artifact_changes(tmp_path, monkeypatch):
    source, remote = tmp_path / "source", tmp_path / "remote"
    unchanged = "etl#unchanged#axon2-core"
    rerun = "train#rerun#axon2-core"
    modified = "inference#modified#axon2-core"
    missing = "backtest#missing#axon2-core"
    for task_id in (unchanged, rerun, modified):
        directory = task(source, task_id)
        shutil.copytree(directory, task_path(remote, task_id))
    task(source, rerun, run_id="second")
    (task_path(source, modified) / "result.txt").write_text("new result", encoding="utf-8")
    task(source, missing)
    task(source, "etl#excluded#axon-v1")
    task(source, "etl#active#axon2-core", state="running")
    sync, client = sync_component(source, monkeypatch, snapshot_index(remote, frozenset({"axon2-core"})))
    async with sync:
        assert sync._pending == {rerun, modified, missing}
        client.run_job.assert_awaited_once_with("task_sync_index", {"task_names": ["axon2-core"]})
    assert not (source / "sync").exists()


@pytest.mark.asyncio
async def test_unreachable_remote_does_not_fail_start_or_queue_a_full_replay(tmp_path, monkeypatch):
    task(tmp_path)
    sync, client = sync_component(tmp_path, monkeypatch, {})
    client.run_job.side_effect = ConnectionError("offline")
    async with sync:
        assert not sync._pending
        await sync.flush()
        assert client.run_job.await_count == 1


@pytest.mark.asyncio
async def test_live_terminal_changes_are_sent_and_deletions_are_ignored(tmp_path, monkeypatch):
    task_id = "etl#demo#axon2-core"
    task(tmp_path, task_id, state="running")
    sync, _ = sync_component(tmp_path, monkeypatch, {})
    sync._send = AsyncMock()
    async with sync:
        sync._pending.add(task_id)
        assert not (await sync.flush()).uploaded
        assert not sync._pending
        task(tmp_path, task_id)
        sync.repository.changes.publish(TaskChanges(frozenset({task_id})))
        await asyncio.sleep(0)
        assert (await sync.flush()).uploaded == [f"etl/{task_id}"]
        shutil.rmtree(task_path(tmp_path, task_id))
        sync._pending.add(task_id)
        assert not (await sync.flush()).uploaded
        assert sync._send.await_count == 1


@pytest.mark.asyncio
async def test_failed_batch_is_dropped_while_unattempted_batch_is_deferred(tmp_path, monkeypatch):
    ids = [f"etl#demo{i}#axon2-core" for i in range(3)]
    for task_id in ids:
        task(tmp_path, task_id)
    sync, _ = sync_component(tmp_path, monkeypatch, {})
    sync.max_archive_bytes = 6500  # One complete Task per archive, with reserved headroom.
    sync.max_archives_per_flush = 2
    sync._pending.update(ids)
    sync._send = AsyncMock(side_effect=[ValueError("synthetic failure"), None, None])
    result = await sync.flush()
    assert result.uploaded == [f"etl/{ids[1]}"]
    assert result.deferred == [f"etl/{ids[2]}"]
    assert sync._pending == {ids[2]}
    assert (await sync.flush()).uploaded == [f"etl/{ids[2]}"]
    assert not sync._pending
    await sync.flush()
    assert sync._send.await_count == 3


@pytest.mark.asyncio
async def test_oversized_snapshot_is_not_requeued(tmp_path, monkeypatch):
    task_id = "etl#demo#axon2-core"
    task(tmp_path, task_id)
    sync, _ = sync_component(tmp_path, monkeypatch, {})
    sync.max_file_bytes = 1
    sync._pending.add(task_id)
    result = await sync.flush()
    assert result.oversized == [f"etl/{task_id}"]
    assert result.rejected
    assert not sync._pending


@pytest.mark.asyncio
async def test_http_roundtrip_reconciles_uploads_and_skips_identical_snapshots(tmp_path, monkeypatch):
    source, remote = tmp_path / "source", tmp_path / "remote"
    source.mkdir()
    remote.mkdir()
    ids = ["etl#demo#axon2-core", "train#demo#axon2-core"]
    for task_id in ids:
        task(source, task_id)
    app = Application(
        workspace_dir=str(remote),
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
    sync = LocalSyncComponent(target="http://remote:1024", task_names=["axon2-core"])
    sync.root = source
    sync.repository = Repository()
    sync.configured_target = SimpleNamespace(address="http://remote:1024", token="secret")
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
        report = await sync.flush()
        assert report.archives == 1
        assert set(report.uploaded) == {f"{task_id.split('#', 1)[0]}/{task_id}" for task_id in ids}
        assert snapshot_index(source, frozenset()) == snapshot_index(remote, frozenset())
        await sync._reconcile()
        assert not sync._pending
        task(source, ids[0], run_id="second")
        await sync._reconcile()
        assert sync._pending == {ids[0]}
        await sync.flush()
        assert snapshot_index(source, frozenset()) == snapshot_index(remote, frozenset())


def test_receiver_refuses_to_replace_an_active_task(tmp_path):
    source, remote = tmp_path / "source", tmp_path / "remote"
    task_id = "etl#demo#axon2-core"
    task(source, task_id)
    task(remote, task_id, state="running", run_id="active")
    archive = tmp_path / "sync.tar.gz"
    build_archive({task_id: plan_task(source, task_id, 100_000)}, [task_id], archive)
    with pytest.raises(ValueError, match="active Task"):
        TaskArchiveApplier(remote).apply(archive, [])
    assert '"active"' in (task_path(remote, task_id) / "metadata.json").read_text()


def test_index_skips_a_changing_task_without_losing_stable_tasks(tmp_path, monkeypatch):
    changing = "etl#changing#axon2-core"
    stable = "etl#stable#axon2-core"
    directory = task(tmp_path, changing)
    task(tmp_path, stable)
    from axonx.task.sync import index

    original = index.file_sha256

    def digest(path):
        result = original(path)
        if path.parent == directory:
            (directory / "late.txt").write_text("changed", encoding="utf-8")
        return result

    monkeypatch.setattr(index, "file_sha256", digest)
    assert set(snapshot_index(tmp_path, frozenset())) == {stable}


@pytest.mark.asyncio
async def test_planning_failure_does_not_drop_other_tasks_or_retry(tmp_path, monkeypatch):
    ids = ["etl#bad#axon2-core", "etl#good#axon2-core"]
    for task_id in ids:
        task(tmp_path, task_id)
    sync, _ = sync_component(tmp_path, monkeypatch, {})
    sync._pending.update(ids)
    sync._send = AsyncMock()
    from axonx.components.sync import local

    original = local.plan_task

    def plan(root, task_id, budget):
        if task_id == ids[0]:
            raise PermissionError("synthetic inaccessible artifact")
        return original(root, task_id, budget)

    monkeypatch.setattr(local, "plan_task", plan)
    assert (await sync.flush()).uploaded == [f"etl/{ids[1]}"]
    assert not sync._pending
