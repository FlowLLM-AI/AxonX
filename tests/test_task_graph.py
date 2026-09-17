"""Task artifact graph API contracts."""

import json

from axonx import Application


GRAPH_JOBS = {
    "list_task_graphs": {"steps": [{"backend": "list_task_graphs_step"}]},
    "get_task_graph": {"steps": [{"backend": "get_task_graph_step"}]},
}


def _artifact(root, task_id, source_tasks=()):
    kind, reg_name, *_ = task_id.split("#")
    path = root / kind / task_id / "metadata.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "schema_version": 3,
            "task_id": task_id,
            "task_type": kind,
            "reg_name": reg_name,
            "created_at": "2026-09-16T00:00:00Z",
            "input_params": {"source_tasks": list(source_tasks)},
            "output_params": {"artifacts": {}},
        }),
        encoding="utf-8",
    )


async def test_task_graph_search_and_full_branch(tmp_path):
    etl_one = "etl#etl#one"
    etl_two = "etl#etl#two"
    analysis = "analysis#analysis#one"
    train = "train#train#one"
    predict = "predict#predict#one"
    backtest_one = "backtest#backtest#one"
    backtest_two = "backtest#backtest#two"
    _artifact(tmp_path, etl_one)
    _artifact(tmp_path, etl_two)
    _artifact(tmp_path, analysis, [etl_one])
    _artifact(tmp_path, train, [etl_one])
    _artifact(tmp_path, predict, [train])
    _artifact(tmp_path, backtest_one, [predict])
    _artifact(tmp_path, backtest_two, [predict])
    app = Application(workspace_dir=str(tmp_path), jobs=GRAPH_JOBS)
    await app.start()
    try:
        roots = (await app.run_job("list_task_graphs", offset=0, limit=1)).answer
        found = (await app.run_job("list_task_graphs", q=backtest_two)).answer
        graph = (await app.run_job("get_task_graph", task_id=backtest_two)).answer
    finally:
        await app.close()
    assert roots["total"] == 2
    assert len(roots["items"]) == 1
    assert found["items"][0]["root_id"] == etl_one
    assert graph["root_id"] == etl_one
    assert graph["selected_id"] == backtest_two
    assert {node["task_id"] for node in graph["nodes"]} == {
        etl_one, analysis, train, predict, backtest_one, backtest_two,
    }
    assert {tuple(edge.values()) for edge in graph["edges"]} >= {
        (etl_one, analysis), (predict, backtest_two),
    }


async def test_task_graph_keeps_missing_parent_visible(tmp_path):
    missing = "train#train#deleted"
    orphan = "predict#predict#orphan"
    _artifact(tmp_path, orphan, [missing])
    app = Application(workspace_dir=str(tmp_path), jobs=GRAPH_JOBS)
    await app.start()
    try:
        graph = (await app.run_job("get_task_graph", task_id=orphan)).answer
    finally:
        await app.close()
    assert graph["root_id"] == missing
    assert any(node["task_id"] == missing and node["missing"] for node in graph["nodes"])


async def test_task_graph_supports_multiple_upstreams_of_same_type(tmp_path):
    first = "etl#etl#first"
    second = "etl#etl#second"
    training = "train#train#first"
    analysis = "analysis#analysis#combined"
    _artifact(tmp_path, first)
    _artifact(tmp_path, second)
    _artifact(tmp_path, training)
    _artifact(tmp_path, analysis, [first, second, training])
    app = Application(workspace_dir=str(tmp_path), jobs=GRAPH_JOBS)
    await app.start()
    try:
        listing = (await app.run_job("list_task_graphs")).answer
        graph = (await app.run_job("get_task_graph", task_id=second)).answer
    finally:
        await app.close()
    assert listing["total"] == 1
    assert graph["root_id"] == first
    assert graph["edges"] == [
        {"from": first, "to": analysis},
        {"from": second, "to": analysis},
        {"from": training, "to": analysis},
    ]
