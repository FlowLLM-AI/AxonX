from datetime import UTC, datetime

from axonx.enums import TaskState, TaskType
from axonx.task.query.graph import task_graph
from axonx.task.storage.workspace import TaskMetadata


def status(task_id: str, task_type: TaskType, **config) -> TaskMetadata:
    return TaskMetadata(
        task_id=task_id,
        run_id=task_id,
        task_type=task_type,
        reg_name="example",
        input_params=config,
        state=TaskState.RUNNING,
        created_at=datetime(2026, 9, 20, tzinfo=UTC),
    )


def test_running_task_has_a_provisional_graph_from_status_config():
    source_id = "etl#native#prices"
    task_id = "analysis#native#factor"
    entries = {
        source_id: status(source_id, TaskType.ETL),
        task_id: status(task_id, TaskType.ANALYSIS, source_tasks=source_id),
    }

    graph = task_graph(entries, task_id)

    assert graph.selected_id == task_id
    assert [(edge.from_, edge.to) for edge in graph.edges] == [(source_id, task_id)]
    assert all(node.provisional for node in graph.nodes)
    assert {node.state for node in graph.nodes} == {"running"}


def test_completed_metadata_has_authoritative_lineage():
    source_id = "etl#native#formal"
    task_id = "analysis#native#factor"
    metadata = status(task_id, TaskType.ANALYSIS, source_tasks=source_id)
    metadata.state = TaskState.SUCCEEDED
    graph = task_graph({task_id: metadata}, task_id)
    assert [(edge.from_, edge.to) for edge in graph.edges] == [(source_id, task_id)]
    selected = next(node for node in graph.nodes if node.task_id == task_id)
    assert not selected.provisional
    assert next(node for node in graph.nodes if node.task_id == source_id).missing


def test_task_without_dependencies_is_a_single_node_graph():
    task_id = "base#native#standalone"
    graph = task_graph({task_id: status(task_id, TaskType.BASE)}, task_id)

    assert graph.root_id == task_id
    assert [node.task_id for node in graph.nodes] == [task_id]
    assert graph.edges == []
