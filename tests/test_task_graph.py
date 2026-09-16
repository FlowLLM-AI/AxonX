"""Task artifact graph API contracts."""

import json

from axonx import Application


GRAPH_JOBS = {
    "list_task_graphs": {"steps": [{"backend": "list_task_graphs_step"}]},
    "get_task_graph": {"steps": [{"backend": "get_task_graph_step"}]},
}


def _artifact(root, kind, task_id, parent_key=None, parent_id=None):
    path = root / kind / task_id / "metadata.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "task_id": task_id,
            "task_name": f"alpha158_{kind}",
            "created_at": "2026-09-16T00:00:00Z",
            "source": {parent_key: parent_id} if parent_key else {},
        }),
        encoding="utf-8",
    )


async def test_task_graph_search_and_full_branch(tmp_path):
    _artifact(tmp_path, "etl", "etl#one")
    _artifact(tmp_path, "etl", "etl#two")
    _artifact(tmp_path, "analysis", "analysis#one", "etl_task_id", "etl#one")
    _artifact(tmp_path, "training", "training#one", "etl_task_id", "etl#one")
    _artifact(tmp_path, "predict", "predict#one", "training_task_id", "training#one")
    _artifact(tmp_path, "backtest", "backtest#one", "prediction_task_id", "predict#one")
    _artifact(tmp_path, "backtest", "backtest#two", "prediction_task_id", "predict#one")
    app = Application(workspace_dir=str(tmp_path), jobs=GRAPH_JOBS)
    await app.start()
    try:
        roots = (await app.run_job("list_task_graphs", offset=0, limit=1)).answer
        found = (await app.run_job("list_task_graphs", q="backtest#two")).answer
        graph = (await app.run_job("get_task_graph", task_id="backtest#two")).answer
    finally:
        await app.close()
    assert roots["total"] == 2
    assert len(roots["items"]) == 1
    assert found["items"][0]["root_id"] == "etl#one"
    assert graph["root_id"] == "etl#one"
    assert graph["selected_id"] == "backtest#two"
    assert {node["task_id"] for node in graph["nodes"]} == {
        "etl#one", "analysis#one", "training#one", "predict#one", "backtest#one", "backtest#two",
    }
    assert {tuple(edge.values()) for edge in graph["edges"]} >= {
        ("etl#one", "analysis#one"), ("predict#one", "backtest#two"),
    }


async def test_task_graph_keeps_missing_parent_visible(tmp_path):
    _artifact(tmp_path, "predict", "predict#orphan", "training_task_id", "training#deleted")
    app = Application(workspace_dir=str(tmp_path), jobs=GRAPH_JOBS)
    await app.start()
    try:
        graph = (await app.run_job("get_task_graph", task_id="predict#orphan")).answer
    finally:
        await app.close()
    assert graph["root_id"] == "training#deleted"
    assert any(node["task_id"] == "training#deleted" and node["missing"] for node in graph["nodes"])
