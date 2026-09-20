from datetime import UTC, datetime

from axonx.enums import TaskState, TaskType
from axonx.task.query.graph import task_graph
from axonx.task.storage.workspace import TaskEntry, TaskRecord, TaskStatus


def status(task_id: str, task_type: TaskType, **config) -> TaskStatus:
    return TaskStatus(
        task_id=task_id,
        run_id=task_id,
        task_type=task_type,
        task_name="example",
        config=config,
        state=TaskState.RUNNING,
        created_at=datetime(2026, 9, 20, tzinfo=UTC),
    )


def test_running_task_has_a_provisional_graph_from_status_config():
    source_id = "etl#native#prices"
    task_id = "analysis#native#factor"
    entries = {
        source_id: TaskEntry(status(source_id, TaskType.ETL), None),
        task_id: TaskEntry(
            status(task_id, TaskType.ANALYSIS, source_tasks=[source_id]), None
        ),
    }

    graph = task_graph(entries, task_id)

    assert graph.selected_id == task_id
    assert [(edge.from_, edge.to) for edge in graph.edges] == [(source_id, task_id)]
    assert all(node.provisional for node in graph.nodes)
    assert {node.state for node in graph.nodes} == {"running"}


def test_metadata_lineage_wins_over_provisional_status_config():
    formal_source = "etl#native#formal"
    stale_source = "etl#native#stale"
    task_id = "analysis#native#factor"
    record = TaskRecord(
        task_id=task_id,
        task_type=TaskType.ANALYSIS,
        reg_name="example",
        created_at="2026-09-20T00:00:00+00:00",
        source_tasks=(formal_source,),
    )
    entries = {
        task_id: TaskEntry(
            status(task_id, TaskType.ANALYSIS, source_tasks=[stale_source]), record
        )
    }

    graph = task_graph(entries, task_id)

    assert [(edge.from_, edge.to) for edge in graph.edges] == [
        (formal_source, task_id)
    ]
    selected = next(node for node in graph.nodes if node.task_id == task_id)
    assert not selected.provisional
    assert next(node for node in graph.nodes if node.task_id == formal_source).missing


def test_task_without_dependencies_is_a_single_node_graph():
    task_id = "base#native#standalone"
    graph = task_graph(
        {task_id: TaskEntry(status(task_id, TaskType.BASE), None)}, task_id
    )

    assert graph.root_id == task_id
    assert [node.task_id for node in graph.nodes] == [task_id]
    assert graph.edges == []
