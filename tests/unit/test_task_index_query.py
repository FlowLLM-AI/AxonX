"""Verify lineage projections and event followers against persisted Task snapshots."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from axonx.app.components.task_index.query import TaskQuery, summarize_status, task_sort_key
from axonx.app.components.task_index.stream import TaskEventStream
from axonx.app.core.application import Application
from axonx.task.models.events import LogEvent, ProgressEvent
from axonx.task.models.identity import TaskState, task_type_from_id
from axonx.task.models.lifecycle import DisplayReplica, ReplicaFile, ReplicaLog, TaskMetadata, TaskStepStatus
from axonx.task.storage.logs import LOG_WINDOW_BYTES, TaskJournal, TaskLogReader
from axonx.task.storage.workspace import EVENTS_FILE, METADATA_FILE, task_path, write_task_metadata

NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
async def index(tmp_path):
    app = Application(
        workspace_dir=str(tmp_path),
        log_dir=str(tmp_path / "logs"),
        log_to_console=False,
        log_to_file=False,
        components={"task_index": {"default": {"backend": "local"}}},
    )
    async with app:
        yield app.context.components["task_index"]["default"]


async def test_index_isolates_subscriber_failures_without_dropping_notifications(tmp_path, index):
    index.logger = Mock()
    delivered = []

    def broken(_changes):
        raise ValueError("subscriber failed")

    index.subscribe(broken)
    index.subscribe(delivered.append)
    status = record()
    write_task_metadata(task_path(tmp_path, status.task_id), status)
    await index._refresh()
    assert delivered == [frozenset({status.task_id})]
    index.logger.exception.assert_called_once()
    assert status.task_id in await index.entries()


def record(task_id="base#demo#query", *, upstream_ids=None, **changes):
    return TaskMetadata(
        **{
            "version": 1,
            "task_id": task_id,
            "task_type": task_type_from_id(task_id),
            "reg_name": task_id.split("#")[1],
            "state": TaskState.SUCCEEDED,
            "pid": 1,
            "machine_id": "test",
            "created_at": NOW,
            "process_started_at": NOW,
            "started_at": NOW,
            "input_params": {"upstream_task_ids": [] if upstream_ids is None else upstream_ids},
        }
        | changes
    )


async def test_index_refresh_updates_lineage_without_exposing_mutable_snapshots(tmp_path, index):
    status = record()
    write_task_metadata(task_path(tmp_path, status.task_id), status)
    await index._refresh()
    assert len((await index.graph(status.task_id)).nodes) == 1
    missing = "etl#fetch#missing"
    status.input_params["upstream_task_ids"] = [missing]
    write_task_metadata(task_path(tmp_path, status.task_id), status)
    await index._refresh()
    graph = await index.graph(status.task_id)
    assert {node.task_id for node in graph.nodes} == {status.task_id, missing}
    graph.nodes.clear()
    assert len((await index.context(status.task_id)).graph.nodes) == 2
    entries = await index.entries(state="succeeded")
    entries[status.task_id].input_params.clear()
    assert (await index.entries())[status.task_id].input_params["upstream_task_ids"] == [missing]


@pytest.mark.parametrize("was_indexed", [False, True])
async def test_context_uses_fresh_selected_dependencies_before_the_next_poll(tmp_path, index, was_indexed):
    source = record("etl#fetch#source")
    old_upstream = "etl#fetch#old"
    status = record(upstream_ids=[old_upstream], state=TaskState.RUNNING)
    write_task_metadata(task_path(tmp_path, source.task_id), source)
    if was_indexed:
        write_task_metadata(task_path(tmp_path, status.task_id), status)
    await index._refresh()
    before = await index.entries()
    delivered = []
    index.subscribe(delivered.append)

    status.state = TaskState.SUCCEEDED
    status.input_params["upstream_task_ids"] = [source.task_id]
    write_task_metadata(task_path(tmp_path, status.task_id), status)

    context = await index.context(status.task_id)

    assert context.status == status
    assert {node.task_id for node in context.graph.nodes} == {source.task_id, status.task_id}
    selected = next(node for node in context.graph.nodes if node.task_id == status.task_id)
    assert selected.state == context.status.state
    assert context.relations.direct_upstream == context.relations.all_upstream == [source.task_id]
    assert context.relations.missing == context.relations.provisional == []
    assert await index.entries() == before
    assert not delivered
    await index._refresh()
    assert delivered == [frozenset({status.task_id})]
    assert (await index.graph(status.task_id)) == context.graph


async def test_index_notifies_once_per_change_and_unsubscribes_idempotently(tmp_path, index):
    delivered = []
    unsubscribe = index.subscribe(delivered.append)
    status = record()
    metadata = task_path(tmp_path, status.task_id) / METADATA_FILE
    write_task_metadata(metadata.parent, status)
    await index._refresh()
    await index._refresh()
    assert delivered == [frozenset({status.task_id})]

    metadata.unlink()
    await index._refresh()
    assert delivered == [frozenset({status.task_id})] * 2
    assert await index.entries() == {}
    with pytest.raises(KeyError):
        await index.graph(status.task_id)

    unsubscribe()
    unsubscribe()
    write_task_metadata(metadata.parent, status)
    await index._refresh()
    assert delivered == [frozenset({status.task_id})] * 2


async def collect(stream, task_id):
    async def drain():
        return [event async for event in stream.follow(task_id, 0.001)]

    return await asyncio.wait_for(drain(), timeout=2)


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({}, ["etl#fetch#source", "base#demo#running", "base#demo#query"]),
        ({"task_type": "base"}, ["base#demo#running", "base#demo#query"]),
        ({"state": "succeeded"}, ["etl#fetch#source", "base#demo#query"]),
        ({"task_type": "base", "state": "running"}, ["base#demo#running"]),
        ({"task_type": "etl", "state": "running"}, []),
    ],
)
def test_record_and_summary_queries_share_filters_and_sorting(filters, expected):
    statuses = [record(), record("base#demo#running", state=TaskState.RUNNING), record("etl#fetch#source")]
    query = TaskQuery({status.task_id: status for status in statuses})

    entries = sorted(query.entries(**filters).values(), key=task_sort_key, reverse=True)
    summaries = query.summaries(**filters)

    assert [item.task_id for item in entries] == [item.task_id for item in summaries] == expected
    assert summaries == [summarize_status(item) for item in entries]


def test_summary_queries_do_not_copy_task_outputs():
    output = Mock()
    output.__deepcopy__ = Mock(side_effect=AssertionError("Full outputs must not be copied for summaries"))
    status = record(output_params={"large": output})
    query = TaskQuery({status.task_id: status})

    assert query.summaries() == [summarize_status(status)]
    output.__deepcopy__.assert_not_called()


def test_graph_and_context_include_missing_upstream_but_exclude_unrelated_tasks():
    missing = "etl#fetch#missing"
    left = record("train#model#left", upstream_ids=[missing])
    right = record("train#model#right", upstream_ids=[missing])
    selected = record("predict#model#selected", upstream_ids=[left.task_id])
    downstream = record(
        "backtest#evaluate#downstream", upstream_ids=[selected.task_id, right.task_id], state=TaskState.RUNNING
    )
    unrelated = record()
    entries = {item.task_id: item for item in (unrelated, downstream, selected, right, left)}
    before = {task_id: item.model_dump_json() for task_id, item in entries.items()}

    context = TaskQuery(entries).context(selected)

    assert context.graph.root_id == missing
    assert context.graph.selected_id == selected.task_id
    assert [node.task_id for node in context.graph.nodes] == [
        missing,
        left.task_id,
        right.task_id,
        selected.task_id,
        downstream.task_id,
    ]
    assert context.relations.direct_upstream == [left.task_id]
    assert context.relations.all_upstream == sorted([missing, left.task_id])
    assert context.relations.direct_downstream == [downstream.task_id]
    assert context.relations.missing == [missing]
    assert context.relations.provisional == [downstream.task_id]
    assert context.metadata_path == f"predict/{selected.task_id}/metadata.json"
    assert context.graph.edges[0].model_dump() == {"from": missing, "to": left.task_id}
    assert {task_id: item.model_dump_json() for task_id, item in entries.items()} == before


def test_cycles_and_self_references_have_stable_graphs_and_finite_all_upstream():
    first = record("base#demo#first", upstream_ids=["base#demo#first", "base#demo#second"])
    second = record("base#demo#second", upstream_ids=[first.task_id])
    forward = TaskQuery({item.task_id: item for item in (first, second)})
    reverse = TaskQuery({item.task_id: item for item in (second, first)})

    context = forward.context(first)

    assert context.graph == reverse.graph(first.task_id)
    assert context.graph.root_id == first.task_id
    assert context.relations.all_upstream == [second.task_id]
    assert context.relations.direct_upstream == context.relations.direct_downstream == [second.task_id]
    assert len(context.graph.edges) == 2


def test_mutating_one_graph_response_does_not_change_subsequent_queries():
    source = record("etl#fetch#source")
    selected = record(upstream_ids=[source.task_id])
    query = TaskQuery({item.task_id: item for item in (source, selected)})
    original = query.graph(selected.task_id)
    changed = query.graph(selected.task_id)
    for node in changed.nodes:
        node.upstream_task_ids.clear()
        node.task_name = "changed"
    context = query.context(selected)
    context.status.input_params.clear()

    assert query.graph(selected.task_id) == original
    assert query.context(selected).relations.all_upstream == [source.task_id]


@pytest.mark.parametrize("upstream_ids", [None, {}, "invalid", ["base#demo#same", "base#demo#same"]])
def test_invalid_upstream_ids_do_not_break_queries(upstream_ids):
    status = record(upstream_ids=upstream_ids)
    context = TaskQuery({status.task_id: status}).context(status)
    assert context.graph.root_id == status.task_id
    assert context.graph.edges == context.relations.all_upstream == []


@pytest.mark.parametrize("task_id", ["base#demo#unknown", "etl#fetch#missing"])
def test_graph_requires_a_persisted_selected_task(task_id):
    status = record(upstream_ids=["etl#fetch#missing"])
    with pytest.raises(KeyError, match=task_id):
        TaskQuery({status.task_id: status}).graph(task_id)


def test_child_invocations_and_upstream_dependencies_are_independent():
    parent_id = "base#pipeline#daily"
    etl = record("etl#dataset#daily", parent_task_id=parent_id)
    train = record("train#model#daily", parent_task_id=parent_id, upstream_ids=[etl.task_id])
    parent = record(
        parent_id,
        children=[
            {"node_name": item.reg_name, "attempt": 1, "reg_name": item.reg_name, "child_task_id": item.task_id}
            for item in (etl, train)
        ],
    )
    query = TaskQuery({item.task_id: item for item in (parent, etl, train)})

    parent_graph = query.graph(parent_id)
    assert [node.task_id for node in parent_graph.nodes] == [parent_id]
    assert parent_graph.edges == []
    context = query.context(train)
    assert {node.task_id for node in context.graph.nodes} == {etl.task_id, train.task_id}
    assert [edge.model_dump() for edge in context.graph.edges] == [{"from": etl.task_id, "to": train.task_id}]
    assert context.relations.direct_upstream == context.relations.all_upstream == [etl.task_id]
    assert query.context(etl).relations.direct_downstream == [train.task_id]
    assert context.status.parent_task_id == parent_id
    assert [child.child_task_id for child in parent.children] == [etl.task_id, train.task_id]


def test_summary_bounds_text_and_uses_only_top_level_step_progress():
    status = record(
        input_params={"task_name": "x" * 300},
        output_params={"large": list(range(1000))},
        error="e" * 2000,
        report_kind="online_pipeline",
        replica=DisplayReplica(source_revision="source", policy_revision="policy", files={}),
        steps=[
            TaskStepStatus(name="child", parent="finished"),
            TaskStepStatus(name="finished", finished_at=NOW),
            TaskStepStatus(name="s" * 300, percentage=25),
            TaskStepStatus(name="pending"),
        ],
    )
    before = status.model_dump_json()

    summary = summarize_status(status)

    assert summary.display_name == "x" * 256
    assert summary.error == "e" * 1000
    assert summary.report_kind == "online_pipeline"
    assert summary.is_replica
    assert summary.step_progress.model_dump() == {"current": 2, "total": 3, "name": "s" * 256, "percentage": 25}
    assert not {"input_params", "output_params", "steps", "replica"} & summary.model_dump().keys()
    assert status.model_dump_json() == before


@pytest.mark.parametrize("finished", [False, True])
def test_summary_handles_absent_or_completed_root_steps(finished):
    steps = [TaskStepStatus(name="nested", parent="root")]
    if finished:
        steps.extend(TaskStepStatus(name=name, finished_at=NOW) for name in ("first", "last"))
    summary = summarize_status(record(steps=steps))
    assert summary.display_name == "demo"
    if finished:
        assert summary.step_progress.model_dump() == {"current": 2, "total": 2, "name": "last", "percentage": None}
    else:
        assert summary.step_progress is None


def test_task_order_uses_creation_time_then_id_and_places_undated_records_last():
    undated = record("base#demo#undated", created_at=None)
    earlier = record("base#demo#earlier", created_at=NOW - timedelta(seconds=1))
    first = record("base#demo#first")
    last = record("base#demo#last")
    assert sorted([undated, first, earlier, last], key=task_sort_key, reverse=True) == [last, first, earlier, undated]


async def test_followers_replay_progress_and_multibyte_logs_with_independent_cursors(tmp_path):
    path = tmp_path / "task.log"
    content = "a" * (LOG_WINDOW_BYTES - 1) + "汉字" * 20 + "b" * LOG_WINDOW_BYTES
    path.write_text(content, encoding="utf-8")
    status = record(log_path=str(path))
    directory = task_path(tmp_path, status.task_id)
    write_task_metadata(directory, status)
    progress = ProgressEvent(name="finished", state="done")
    journal = TaskJournal(directory / EVENTS_FILE)
    journal.append(progress)
    with journal.path.open("a", encoding="utf-8") as handle:
        handle.write("malformed\n")
    logger = Mock()
    stream = TaskEventStream(tmp_path, TaskLogReader(tmp_path), AsyncMock(return_value=status), logger)

    first, second = await asyncio.gather(collect(stream, status.task_id), collect(stream, status.task_id))

    assert first == second
    assert first[0] == progress
    assert "".join(event.content for event in first if isinstance(event, LogEvent)) == content
    assert first[-1].next_offset == len(content.encode("utf-8"))
    assert logger.warning.call_count == 2


async def test_terminal_follow_stops_at_its_snapshot_when_a_shared_log_keeps_growing(tmp_path, monkeypatch):
    path = tmp_path / "process.log"
    content = b"x" * (LOG_WINDOW_BYTES + 10)
    path.write_bytes(content)
    status = record(log_path=str(path))
    logs = TaskLogReader(tmp_path)
    read = logs.read_status

    def read_growing_log(*args):
        chunk = read(*args)
        with path.open("ab") as handle:
            handle.write(b"sibling output")
        return chunk

    monkeypatch.setattr(logs, "read_status", read_growing_log)
    stream = TaskEventStream(tmp_path, logs, AsyncMock(return_value=status), Mock())

    events = await collect(stream, status.task_id)

    assert "".join(event.content for event in events).encode() == content
    assert path.stat().st_size > events[-1].next_offset == len(content)


@pytest.mark.parametrize("change_path", [False, True])
async def test_follow_resets_after_log_truncation_or_a_path_change(tmp_path, change_path):
    path = tmp_path / "task.log"
    path.write_text("before")
    running = record(log_path=str(path), state=TaskState.RUNNING)
    replacement = tmp_path / "replacement.log" if change_path else path
    terminal = record(log_path=str(replacement))
    calls = 0

    async def read_metadata(_):
        nonlocal calls
        calls += 1
        if calls == 1:
            return running
        replacement.write_text("end")
        return terminal

    stream = TaskEventStream(tmp_path, TaskLogReader(tmp_path), read_metadata, Mock())

    events = await collect(stream, running.task_id)

    assert [event.content for event in events] == ["before", "end"]
    assert events[-1].reset is (not change_path)
    assert events[-1].next_offset == 3


async def test_follow_preserves_replica_source_offsets(tmp_path):
    content = b"replica output"
    start = 100
    end = start + len(content)
    status = record(
        replica=DisplayReplica(
            source_revision="source",
            policy_revision="policy",
            files={"display.log": ReplicaFile(size=len(content), revision="1:1")},
            log=ReplicaLog(path="display.log", start=start, end=end),
        )
    )
    directory = task_path(tmp_path, status.task_id)
    write_task_metadata(directory, status)
    (directory / "display.log").write_bytes(content)
    stream = TaskEventStream(tmp_path, TaskLogReader(tmp_path / "logs"), AsyncMock(return_value=status), Mock())

    (event,) = await collect(stream, status.task_id)

    assert event.content.encode() == content
    assert event.reset
    assert (event.start_offset, event.next_offset, event.file_size) == (start, end, end)


async def test_unreadable_logs_warn_once_and_do_not_prevent_completion(tmp_path):
    running = record(log_path=str(tmp_path.parent / "outside.log"), state=TaskState.RUNNING)
    terminal = running.model_copy(update={"state": TaskState.SUCCEEDED})
    read = AsyncMock(side_effect=[running, running, terminal])
    logger = Mock()
    stream = TaskEventStream(tmp_path, TaskLogReader(tmp_path), read, logger)

    assert await collect(stream, running.task_id) == []
    logger.warning.assert_called_once()
    assert read.await_count == 3


@pytest.mark.parametrize("interval", [0, -1, float("nan"), float("inf")])
async def test_follow_rejects_invalid_poll_intervals(tmp_path, interval):
    read = AsyncMock()
    stream = TaskEventStream(tmp_path, TaskLogReader(tmp_path), read, Mock())
    with pytest.raises(ValueError, match="finite and positive"):
        await anext(stream.follow("base#demo#query", interval))
    read.assert_not_awaited()
