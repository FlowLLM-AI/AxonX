"""Live display snapshots preserve Run identity, bounded logs and atomic groups."""

import socket
import tarfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from axonx.app.components.client import HttpClient
from axonx.app.components.service import HttpService
from axonx.app.components.sync import LocalSyncComponent
from axonx.app.config import ApplicationConfig
from axonx.app.core import Application
from axonx.common.fs import atomic_write_json, file_sha256
from axonx.task.enums import TaskState, TaskType
from axonx.task.schemas.lifecycle import ChildTaskRecord, TaskMetadata
from axonx.task.schemas.protocol import fingerprint
from axonx.task.storage.artifacts import artifact_record
from axonx.task.storage.logs import TaskLogReader
from axonx.task.storage.workspace import read_entry, task_path, write_task_metadata
from axonx.task.sync import TaskArchiveApplier, build_archive
from axonx.task.sync.errors import ReplicaBudgetError, SnapshotChangedError
from axonx.task.sync.index import snapshot_index, verify_replica
from axonx.task.sync.replica import prepare_group

PARENT = "composite#a_stock_online#axon2-core"
CHILD = "inference#a_stock_online_predict#axon-v1-1445"
BUDGET = 8 * 1024 * 1024


def source(root):
    logs = root / "logs"
    logs.mkdir(parents=True)
    for identity in (PARENT, CHILD):
        directory = task_path(root, identity)
        directory.mkdir(parents=True)
        log = logs / f"{identity}.log"
        log.write_text("下载中\n", encoding="utf-8")
        (directory / "result.txt").write_text("committed result")
        status = TaskMetadata(
            machine_id="test-machine",
            process_started_at="2026-01-01T00:00:00Z",
            version=1,
            task_id=identity,
            task_type=identity.split("#", 1)[0],
            run_id=identity + "-run",
            state="running",
            pid=12345,
            log_path=str(log),
            output_params={"artifacts": {"result": artifact_record(directory / "result.txt", directory)}},
        )
        if identity == PARENT:
            status.report_kind = "online_pipeline"
            status.children = [
                ChildTaskRecord(
                    node_name="model",
                    task="a_stock_online_predict",
                    task_id=CHILD,
                    run_id=CHILD + "-run",
                    attempt=1,
                    state="running",
                )
            ]
        write_task_metadata(directory, status)
    return TaskLogReader(logs)


def capture(root, staging, logs, remote=None):
    plans = prepare_group(root, PARENT, staging, BUDGET, logs, remote or {})
    archive = staging / "sync.tar.gz"
    build_archive(plans, sorted(plans), archive)
    return archive


def update(root, identity, **changes):
    status = read_entry(root, identity)
    for key, value in changes.items():
        setattr(status, key, TaskState(value) if key == "state" else value)
    write_task_metadata(task_path(root, identity), status)


def test_live_delta_heartbeat_completion_and_stale_packet(tmp_path):
    root, remote = tmp_path / "source", tmp_path / "remote"
    remote.mkdir()
    logs = source(root)
    apply = TaskArchiveApplier(remote, BUDGET)
    first = capture(root, tmp_path / "first", logs)
    apply.apply(first, [])
    for identity in (PARENT, CHILD):
        status = read_entry(remote, identity)
        assert status.state == "running" and status.pid == 12345 and status.log_path == ""
        verify_replica(remote, identity)
        assert logs.read_status(remote, status).content == "下载中\n"
    bases = snapshot_index(remote, frozenset(), frozenset({PARENT}))
    second = capture(root, tmp_path / "second", logs, bases)
    with tarfile.open(second) as archive:
        assert all(name.endswith("metadata.json") for name in archive.getnames())
    old_time = read_entry(remote, PARENT).replica.snapshot.captured_at
    apply.apply(second, [])
    assert read_entry(remote, PARENT).replica.snapshot.captured_at > old_time
    with pytest.raises(ValueError, match="Stale"):
        apply.apply(first, [])
    for identity in (PARENT, CHILD):
        update(root, identity, state="succeeded")
    final = capture(
        root,
        tmp_path / "final",
        logs,
        snapshot_index(remote, frozenset(), frozenset({PARENT})),
    )
    apply.apply(final, [])
    assert read_entry(remote, CHILD).state == "succeeded"
    update(root, CHILD, state="running")
    rollback = capture(root, tmp_path / "rollback", logs)
    with pytest.raises(ValueError, match="regress"):
        apply.apply(rollback, [])
    assert read_entry(remote, CHILD).state == "succeeded"


def test_log_tail_original_offsets_utf8_growth_and_gap(tmp_path):
    root, remote = tmp_path / "source", tmp_path / "remote"
    remote.mkdir()
    logs = source(root)
    log = logs.path(read_entry(root, PARENT))
    data = ("下载中\n" * 180_000).encode()
    log.write_bytes(data)
    applier = TaskArchiveApplier(remote, BUDGET)
    applier.apply(capture(root, tmp_path / "one", logs), [])
    status = read_entry(remote, PARENT)
    assert status.replica.log.start == len(data) - (1024 * 1024)
    chunk = logs.read_status(remote, status, -1, 17)
    assert "�" not in chunk.content
    assert chunk.next_offset == len(data)
    assert chunk.file_size == len(data)
    assert len(chunk.content.encode()) <= 20
    assert logs.read_status(remote, status, 0).reset
    at = chunk.next_offset
    with log.open("ab") as stream:
        stream.write("完成\n".encode())
    applier.apply(
        capture(
            root,
            tmp_path / "two",
            logs,
            snapshot_index(remote, frozenset(), frozenset({PARENT})),
        ),
        [],
    )
    chunk = logs.read_status(remote, read_entry(remote, PARENT), at)
    assert chunk.content == "完成\n" and not chunk.reset
    with pytest.raises(ValueError, match="range"):
        logs.read_status(remote, status, -2)


def test_exact_children_native_active_and_corrupt_delta(tmp_path):
    root, remote = tmp_path / "source", tmp_path / "remote"
    remote.mkdir()
    logs = source(root)
    applier = TaskArchiveApplier(remote, BUDGET)
    first = capture(root, tmp_path / "one", logs)
    native = task_path(remote, CHILD)
    native.mkdir(parents=True)
    write_task_metadata(native, read_entry(root, CHILD))
    with pytest.raises(ValueError, match="active Task"):
        applier.apply(first, [])
    assert read_entry(remote, PARENT) is None
    assert read_entry(remote, CHILD).replica is None
    write_task_metadata(
        native,
        read_entry(root, CHILD).model_copy(update={"state": TaskState.SUCCEEDED}),
    )
    applier.apply(first, [])
    bases = snapshot_index(remote, frozenset(), frozenset({PARENT}))
    delta = capture(root, tmp_path / "two", logs, bases)
    (native / "result.txt").write_text("corrupt")
    with pytest.raises(ValueError, match="corrupt"):
        applier.apply(delta, [])
    assert CHILD not in snapshot_index(remote, frozenset(), frozenset({PARENT}))
    update(root, CHILD, run_id="replacement")
    with pytest.raises(SnapshotChangedError, match="Run is unavailable"):
        capture(root, tmp_path / "bad", logs)


def test_budget_and_missing_child_fail_without_partial_snapshot(tmp_path):
    root = tmp_path / "source"
    logs = source(root)
    with pytest.raises(ReplicaBudgetError):
        prepare_group(root, PARENT, tmp_path / "small", 1024, logs, {})
    update(root, CHILD, run_id="new-child")
    with pytest.raises(SnapshotChangedError):
        prepare_group(root, PARENT, tmp_path / "bad", BUDGET, logs, {})


def test_group_budget_keeps_status_logs_and_marks_omitted_data(tmp_path):
    root, remote, staging = (
        tmp_path / "source",
        tmp_path / "remote",
        tmp_path / "staging",
    )
    remote.mkdir()
    logs = source(root)
    for identity in (PARENT, CHILD):
        directory = task_path(root, identity)
        large = directory / "large.bin"
        large.write_bytes(b"x" * 120_000)
        status = read_entry(root, identity)
        status.output_params["artifacts"]["large"] = artifact_record(large, directory)
        write_task_metadata(directory, status)
    (task_path(root, CHILD) / "result.txt").unlink()
    budget = 180_000
    plans = prepare_group(root, PARENT, staging, budget, logs, {})
    archive = staging / "group.tar.gz"
    build_archive(plans, sorted(plans), archive)
    TaskArchiveApplier(remote, budget).apply(archive, [])
    for identity in (PARENT, CHILD):
        status = read_entry(remote, identity)
        assert status.state == "running"
        assert status.replica.omitted["large.bin"] == "transfer budget"
        assert logs.read_status(remote, status).content == "下载中\n"
        verify_replica(remote, identity)
    assert read_entry(remote, CHILD).replica.omitted["result.txt"] == "published artifact is missing"


def test_completed_shared_child_can_sync_independently_without_blocking_batch(tmp_path):
    from axonx.task.sync.replica import prepare_replica

    root, remote = tmp_path / "source", tmp_path / "remote"
    remote.mkdir()
    logs = source(root)
    for identity in (PARENT, CHILD):
        update(root, identity, state="succeeded")
    apply = TaskArchiveApplier(remote, BUDGET)
    apply.apply(capture(root, tmp_path / "group", logs), [])
    staging = tmp_path / "independent"
    plans = {
        identity: prepare_replica(root, identity, task_path(staging, identity), BUDGET) for identity in (CHILD, PARENT)
    }
    archive = staging / "batch.tar.gz"
    build_archive(plans, sorted(plans), archive)
    apply.apply(archive, [])
    for identity in (PARENT, CHILD):
        assert read_entry(remote, identity).replica.snapshot is None
        verify_replica(remote, identity)
    # An active snapshot must not regress the completed independent replica.
    update(root, CHILD, state="running")
    with pytest.raises(ValueError, match="regress"):
        apply.apply(capture(root, tmp_path / "regress", logs), [])


def test_shared_child_can_move_between_live_parents_but_not_sources(tmp_path):
    root, remote = tmp_path / "source", tmp_path / "remote"
    remote.mkdir()
    logs = source(root)
    apply = TaskArchiveApplier(remote, BUDGET)
    apply.apply(capture(root, tmp_path / "first", logs), [])
    second = "composite#a_stock_compare#axon2-core"
    parent = read_entry(root, PARENT).model_copy(deep=True, update={"task_id": second, "run_id": "second-parent"})
    write_task_metadata(task_path(root, second), parent)
    staging = tmp_path / "second"
    plans = prepare_group(root, second, staging, BUDGET, logs, {})
    archive = staging / "second.tar.gz"
    build_archive(plans, sorted(plans), archive)
    apply.apply(archive, [])
    assert read_entry(remote, CHILD).replica.snapshot.root_task_id == second
    # A different workspace still cannot overwrite a live replica.
    other = tmp_path / "other"
    other_logs = source(other)
    with pytest.raises(ValueError, match="conflicting"):
        apply.apply(capture(other, tmp_path / "other-packet", other_logs), [])


@pytest.mark.asyncio
async def test_live_http_flush_follows_children_outside_terminal_filter_and_retries(tmp_path, monkeypatch):
    root, remote = tmp_path / "source", tmp_path / "remote"
    remote.mkdir()
    source(root)
    app = Application(
        workspace_dir=str(remote),
        transfer_budget_bytes=BUDGET,
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
    sync = LocalSyncComponent(target="http://remote:1024", task_names=["axon2-core"], live_task_ids=[PARENT])
    sync.root = root
    sync.app_context = SimpleNamespace(
        app_config=ApplicationConfig(transfer_budget_bytes=BUDGET, log_dir=str(root / "logs"))
    )
    sync._needs_reconcile = False
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
        first = await sync.flush()
        assert len(first.uploaded) == 2 and first.archives == 1
        assert read_entry(remote, CHILD).state == "running"
        original_send = sync._send
        monkeypatch.setattr(sync, "_send", AsyncMock(side_effect=ConnectionError("offline")))
        assert (await sync.flush()).deferred
        monkeypatch.setattr(sync, "_send", original_send)
        assert len((await sync.flush()).uploaded) == 2
        # Native tasks still wait for terminal state under the same component.
        assert sync._settled([PARENT, CHILD]) == [PARENT]


@pytest.mark.asyncio
async def test_offline_live_group_never_falls_back_to_terminal_child_transfer(tmp_path, monkeypatch):
    root = tmp_path / "source"
    source(root)
    update(root, CHILD, state="succeeded")
    sync = LocalSyncComponent(target="http://remote:1024", live_task_ids=[PARENT])
    sync.root = root
    sync._needs_reconcile = False
    sync._pending.add(CHILD)
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.run_job.side_effect = ConnectionError("offline")
    monkeypatch.setattr(sync, "_client", lambda: client)
    transfer = AsyncMock()
    monkeypatch.setattr(sync, "_transfer", transfer)
    assert (await sync.flush()).deferred
    transfer.assert_not_called()


def test_repeated_named_children_sync_latest_run_and_keep_attempt_history(tmp_path):
    root, remote = tmp_path / "source", tmp_path / "remote"
    remote.mkdir()
    logs = source(root)
    parent = read_entry(root, PARENT)
    first = parent.children[0]
    parent.children.append(first.model_copy(update={"run_id": "second-attempt", "attempt": 2}))
    write_task_metadata(task_path(root, PARENT), parent)
    update(root, CHILD, run_id="second-attempt")
    TaskArchiveApplier(remote, BUDGET).apply(capture(root, tmp_path / "capture", logs), [])
    assert [child.run_id for child in read_entry(remote, PARENT).children] == [
        first.run_id,
        "second-attempt",
    ]
    assert read_entry(remote, CHILD).run_id == "second-attempt"


@pytest.mark.asyncio
async def test_live_groups_with_shared_child_use_separate_snapshots_and_archives(tmp_path, monkeypatch):
    root, remote = tmp_path / "source", tmp_path / "remote"
    remote.mkdir()
    source(root)
    second = "composite#a_stock_compare#axon2-core"
    parent = read_entry(root, PARENT).model_copy(deep=True, update={"task_id": second, "run_id": "second-parent"})
    write_task_metadata(task_path(root, second), parent)
    sync = LocalSyncComponent(target="remote:1024", live_task_ids=[PARENT, second])
    sync.root = root
    sync.app_context = SimpleNamespace(
        app_config=ApplicationConfig(transfer_budget_bytes=BUDGET, log_dir=str(root / "logs"))
    )
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.run_job.return_value = SimpleNamespace(success=True, answer={"transfer_budget_bytes": BUDGET, "tasks": {}})
    monkeypatch.setattr(sync, "_client", lambda: client)
    applied = []

    async def send(_client, archive):
        applied.append(TaskArchiveApplier(remote, BUDGET).apply(archive, []).applied)

    monkeypatch.setattr(sync, "_send", send)
    report = await sync.flush()
    assert not report.deferred and not report.rejected
    assert report.archives == 2
    assert len(applied) == 2
    assert all(f"inference/{CHILD}" in batch and len(batch) == 2 for batch in applied)
    for identity in (PARENT, second, CHILD):
        verify_replica(remote, identity)


@pytest.mark.asyncio
async def test_shared_archive_budget_rotates_between_active_groups_and_terminal_tasks(tmp_path, monkeypatch):
    root, remote = tmp_path / "source", tmp_path / "remote"
    remote.mkdir()
    source(root)
    second, terminal = "composite#z_online#axon2-core", "base#demo#standalone"
    for identity in (PARENT, second, terminal):
        status = read_entry(root, PARENT).model_copy(deep=True, update={"task_id": identity, "children": []})
        status.task_type = TaskType(identity.split("#", maxsplit=1)[0])
        status.output_params = {}
        if identity == terminal:
            status.state = TaskState.SUCCEEDED
        else:
            log = root / "logs" / (identity + ".log")
            log.write_text("x" * 15_000)
            status.log_path = str(log)
        write_task_metadata(task_path(root, identity), status)
    budget = 40 * 1024
    sync = LocalSyncComponent(target="remote:1024", live_task_ids=[PARENT, second], max_archives_per_flush=1)
    sync.root = root
    sync.app_context = SimpleNamespace(
        app_config=ApplicationConfig(transfer_budget_bytes=budget, log_dir=str(root / "logs"))
    )
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.run_job.side_effect = lambda *_args, **_kwargs: SimpleNamespace(
        success=True,
        answer={
            "transfer_budget_bytes": budget,
            "tasks": snapshot_index(remote, frozenset(), frozenset({PARENT, second})),
        },
    )
    monkeypatch.setattr(sync, "_client", lambda: client)
    apply = TaskArchiveApplier(remote, budget)

    async def send(_client, archive):
        apply.apply(archive, [])

    monkeypatch.setattr(sync, "_send", send)
    for _ in range(3):
        await sync.flush()
    assert all(read_entry(remote, identity) is not None for identity in (PARENT, second, terminal))
    assert read_entry(remote, PARENT).state == TaskState.RUNNING


def test_completed_unchanged_group_does_not_resend(tmp_path):
    root, remote = tmp_path / "source", tmp_path / "remote"
    remote.mkdir()
    logs = source(root)
    for identity in (PARENT, CHILD):
        update(root, identity, state="succeeded")
    TaskArchiveApplier(remote, BUDGET).apply(capture(root, tmp_path / "first", logs), [])
    index = snapshot_index(remote, frozenset(), frozenset({PARENT}))
    assert not prepare_group(root, PARENT, tmp_path / "unchanged", BUDGET, logs, index)


def test_completed_replica_can_join_group_using_verified_delta_files(tmp_path):
    from axonx.task.sync.replica import prepare_replica

    root, remote, staging = (
        tmp_path / "source",
        tmp_path / "remote",
        tmp_path / "terminal",
    )
    remote.mkdir()
    logs = source(root)
    for identity in (PARENT, CHILD):
        update(root, identity, state="succeeded")
    plans = {
        identity: prepare_replica(root, identity, task_path(staging, identity), BUDGET) for identity in (PARENT, CHILD)
    }
    archive = staging / "terminal.tar.gz"
    build_archive(plans, list(plans), archive)
    apply = TaskArchiveApplier(remote, BUDGET)
    apply.apply(archive, [])
    assert read_entry(remote, CHILD).replica.snapshot is None
    index = snapshot_index(remote, frozenset())
    grouped = capture(root, tmp_path / "grouped", logs, index)
    with tarfile.open(grouped) as packet:
        assert not any(name.endswith("result.txt") for name in packet.getnames())
    apply.apply(grouped, [])
    for identity in (PARENT, CHILD):
        assert read_entry(remote, identity).replica.snapshot.root_task_id == PARENT
        verify_replica(remote, identity)


def test_completed_group_log_offset_change_is_not_skipped_for_identical_tail(tmp_path):
    root, remote = tmp_path / "source", tmp_path / "remote"
    remote.mkdir()
    logs = source(root)
    for identity in (PARENT, CHILD):
        update(root, identity, state="succeeded")
    log = logs.path(read_entry(root, PARENT))
    log.write_bytes(b"x" * (1024 * 1024))
    apply = TaskArchiveApplier(remote, BUDGET)
    apply.apply(capture(root, tmp_path / "first", logs), [])
    previous = read_entry(remote, PARENT)
    with log.open("ab") as stream:
        stream.write(b"x")
    index = snapshot_index(remote, frozenset(), frozenset({PARENT}))
    plans = prepare_group(root, PARENT, tmp_path / "next", BUDGET, logs, index)
    assert plans
    status = read_entry(tmp_path / "next", PARENT)
    assert status.replica.log.end == previous.replica.log.end + 1
    assert status.replica.source_revision != previous.replica.source_revision


def test_legacy_live_replica_keeps_workspace_identity_during_upgrade(tmp_path):
    root, remote = tmp_path / "source", tmp_path / "remote"
    remote.mkdir()
    logs = source(root)
    apply = TaskArchiveApplier(remote, BUDGET)
    apply.apply(capture(root, tmp_path / "first", logs), [])
    old_source_id = fingerprint({"host": socket.gethostname(), "workspace": str(root.resolve())})
    for identity in (PARENT, CHILD):
        directory = task_path(remote, identity)
        value = read_entry(remote, identity).model_dump(mode="json")
        replica = value["replica"]
        replica["snapshot"]["source_id"] = old_source_id
        replica["source_digest"] = replica.pop("source_revision")
        replica["policy_digest"] = fingerprint(replica.pop("policy_revision"))
        for name, record in replica["files"].items():
            record.pop("revision")
            record["sha256"] = file_sha256(directory / name)
        atomic_write_json(directory / "metadata.json", value)
    index = snapshot_index(remote, frozenset(), frozenset({PARENT}))
    assert index[CHILD]["source_revision"].startswith("legacy:")
    apply.apply(capture(root, tmp_path / "upgrade", logs, index), [])
    for identity in (PARENT, CHILD):
        status = read_entry(remote, identity)
        assert status.replica.snapshot.source_id == old_source_id
        assert not status.replica.source_revision.startswith("legacy:")
        verify_replica(remote, identity)


def test_idle_live_snapshot_reuses_manifest_without_preparing_files(tmp_path, monkeypatch):
    root, remote = tmp_path / "source", tmp_path / "remote"
    remote.mkdir()
    logs = source(root)
    TaskArchiveApplier(remote, BUDGET).apply(capture(root, tmp_path / "first", logs), [])
    index = snapshot_index(remote, frozenset(), frozenset({PARENT}))

    def unexpected(*_args, **_kwargs):
        pytest.fail("Unchanged snapshot prepared or sampled files")

    monkeypatch.setattr("axonx.task.sync.replica.snapshot_file", unexpected)
    monkeypatch.setattr("axonx.task.sync.replica.write_sample", unexpected)
    plans = prepare_group(root, PARENT, tmp_path / "idle", BUDGET, logs, index)
    assert plans
    assert all([item.relative for item in plan.files] == ["metadata.json"] for plan in plans.values())
